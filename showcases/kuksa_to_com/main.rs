// *******************************************************************************
// Copyright (c) 2026 Contributors to the Eclipse Foundation
//
// See the NOTICE file(s) distributed with this work for additional
// information regarding copyright ownership.
//
// This program and the accompanying materials are made available under the
// terms of the Apache License 2.0 which is available at
// https://www.apache.org/licenses/LICENSE-2.0
//
// SPDX-License-Identifier: Apache-2.0
// *******************************************************************************

use kuksa_vehicle_gen::{VehicleInterface, VssSignal};
use score_com::{
    Builder, InstanceSpecifier, LolaRuntimeBuilderImpl, Producer, Publisher, Runtime, RuntimeBuilder,
    SampleMaybeUninit, SampleMut,
};
use std::collections::HashMap;
use std::env;
use std::path::PathBuf;
use std::process::Command;
use std::thread;
use std::time::Duration;

const INSTANCE_SPECIFIER: &str = "/Vehicle/Service1/Instance";
const PUBLISH_INTERVAL_MS: u64 = 500;

// Default set of watched VSS paths, used only when KUKSA_VSS_PATHS is unset.
// Add or remove any VSS path here (or via the env var) -- the mw::com side
// carries a generic (path, value) pair, so no code change is needed to
// support a new signal.
const DEFAULT_VSS_PATHS: &[&str] = &[
    "Vehicle.Speed",
    "Vehicle.Powertrain.CombustionEngine.Speed",
    "Vehicle.Cabin.Door.Row1.Left.IsOpen",
    "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current",
];

// This is the KUKSA boundary: each poll shells out to the official
// `kuksa-databroker-cli` image to `get` the current value of each watched
// VSS path from a running Databroker. This is a real client hitting the real
// gRPC server (not simulated), so values set via `publish`/`set`/`feed` in
// your own KUKSA CLI session show up here. It requires Docker, a `kuksa`
// Docker network, and a Databroker container reachable at KUKSA_SERVER.

fn kuksa_cli_image() -> String {
    env::var("KUKSA_DATABROKER_CLI_IMAGE")
        .unwrap_or_else(|_| "ghcr.io/eclipse-kuksa/kuksa-databroker-cli:main".to_string())
}

fn kuksa_docker_network() -> String {
    env::var("KUKSA_DOCKER_NETWORK").unwrap_or_else(|_| "kuksa".to_string())
}

fn kuksa_server() -> String {
    env::var("KUKSA_SERVER").unwrap_or_else(|_| "Server:55555".to_string())
}

// Comma-separated list of VSS paths to watch, e.g.:
//   KUKSA_VSS_PATHS="Vehicle.Speed,Vehicle.VehicleIdentification.VIN"
// Falls back to DEFAULT_VSS_PATHS when unset.
fn watched_vss_paths() -> Vec<String> {
    match env::var("KUKSA_VSS_PATHS") {
        Ok(value) => value
            .split(',')
            .map(str::trim)
            .filter(|path| !path.is_empty())
            .map(str::to_string)
            .collect(),
        Err(_) => DEFAULT_VSS_PATHS.iter().map(|path| path.to_string()).collect(),
    }
}

// Runs `kuksa-databroker-cli get <path>` and returns the raw value text, or
// None if the path is not reachable or its value is not currently available.
fn kuksa_get(path: &str) -> Option<String> {
    let output = Command::new("docker")
        .args([
            "run",
            "--rm",
            "-t", // the CLI errors with "Not a tty" without an allocated pseudo-tty
            "--network",
            &kuksa_docker_network(),
            &kuksa_cli_image(),
            "--server",
            &kuksa_server(),
            "get",
            path,
        ])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    for line in stdout.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix(path) {
            let rest = rest.trim_start();
            let value = rest.strip_prefix(':')?.trim();
            if value.is_empty() || value.contains("NotAvailable") {
                return None;
            }
            return Some(value.to_string());
        }
    }
    None
}

fn config_path() -> PathBuf {
    env::var_os("MW_COM_CONFIG_FILE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("showcases/kuksa_to_com/etc/mw_com_config.json"))
}

fn main() {
    let config_path = config_path();
    let mut runtime_builder: LolaRuntimeBuilderImpl = LolaRuntimeBuilderImpl::new();
    runtime_builder.load_config(&config_path);
    let runtime = runtime_builder
        .build()
        .expect("failed to build the S-CORE mw::com runtime");

    let instance = InstanceSpecifier::new(INSTANCE_SPECIFIER)
        .expect("invalid mw::com instance specifier");
    let producer = runtime
        .producer_builder::<VehicleInterface>(instance)
        .build()
        .expect("failed to build the mw::com provider")
        .offer()
        .expect("failed to offer the mw::com service");

    let paths = watched_vss_paths();
    println!(
        "offering VehicleInterface at {INSTANCE_SPECIFIER}; polling {} KUKSA path(s) at {} via {} every {PUBLISH_INTERVAL_MS}ms (Ctrl+C to stop)",
        paths.len(),
        kuksa_server(),
        kuksa_cli_image()
    );

    // Tracks the last value seen per path so we only publish/print on an
    // actual change, instead of flooding the log and the mw::com channel
    // with the same unchanged value every poll.
    let mut last_seen: HashMap<&str, Option<String>> = HashMap::new();

    loop {
        for path in &paths {
            let value = kuksa_get(path);
            let previous = last_seen.get(path.as_str()).cloned().unwrap_or(None);
            if value == previous {
                continue;
            }

            match &value {
                Some(v) => {
                    producer
                        .vss_signal
                        .allocate()
                        .expect("failed to allocate vss_signal sample")
                        .write(VssSignal::new(path, v))
                        .send()
                        .expect("failed to publish vss_signal sample");
                    println!("published {path} = {v}");
                }
                None => {
                    println!("{path} not available");
                }
            }
            last_seen.insert(path.as_str(), value);
        }
        thread::sleep(Duration::from_millis(PUBLISH_INTERVAL_MS));
    }
}
