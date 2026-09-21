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
use std::fs::File;
use std::io::{self, BufRead};
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

// Default location of a VSS json tree (e.g. an exported vss.json) used to
// auto-discover every signal to watch. Any current or future signal added to
// this file is picked up automatically, without touching code or generating
// an intermediate paths file.
fn vss_json_path() -> PathBuf {
    env::var_os("KUKSA_VSS_JSON_FILE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("demo/mw_com_setup/etc/vss.json"))
}

// Finds every `"<key>": "<value>"` occurrence in a VSS json file and returns
// (byte offset, value) pairs in file order. This is a lightweight,
// dependency-free stand-in for a full JSON parser -- sufficient because VSS
// json only ever uses `type`/`name` as simple quoted string fields.
fn find_all_key_values(content: &str, key: &str) -> Vec<(usize, String)> {
    let pattern = format!("\"{key}\"");
    let mut results = Vec::new();
    let mut start = 0;
    while let Some(idx) = content[start..].find(&pattern) {
        let abs_idx = start + idx;
        let after = &content[abs_idx + pattern.len()..];
        if let Some(colon_idx) = after.find(':') {
            let after_colon = after[colon_idx + 1..].trim_start();
            if let Some(rest) = after_colon.strip_prefix('"') {
                if let Some(end_quote) = rest.find('"') {
                    results.push((abs_idx, rest[..end_quote].to_string()));
                }
            }
        }
        start = abs_idx + pattern.len();
    }
    results
}

// Walks a VSS json tree and returns every leaf signal's dotted path (i.e.
// every node whose `type` is not `branch`), covering the entire tree -- any
// signal present in the file is included, including ones added in the future.
fn vss_leaf_paths_from_json(content: &str) -> Vec<String> {
    let types = find_all_key_values(content, "type");
    let names = find_all_key_values(content, "name");
    let mut leaves = Vec::new();
    let mut type_idx = 0;
    let mut current_type: Option<&str> = None;
    for (name_pos, name_val) in &names {
        while type_idx < types.len() && types[type_idx].0 < *name_pos {
            current_type = Some(types[type_idx].1.as_str());
            type_idx += 1;
        }
        if current_type != Some("branch") {
            leaves.push(name_val.clone());
        }
    }
    leaves
}

// Comma-separated list of VSS paths to watch, e.g.:
//   KUKSA_VSS_PATHS="Vehicle.Speed,Vehicle.VehicleIdentification.VIN"
// Resolution order: KUKSA_VSS_PATHS_FILE (explicit newline list) ->
// KUKSA_VSS_PATHS (explicit comma list) -> auto-discovery from a VSS json
// tree (KUKSA_VSS_JSON_FILE or the checked-in default) -> DEFAULT_VSS_PATHS.
fn watched_vss_paths() -> Vec<String> {
    if let Ok(file) = env::var("KUKSA_VSS_PATHS_FILE") {
        if let Ok(f) = File::open(file) {
            let reader = io::BufReader::new(f);
            let mut paths = Vec::new();
            for line in reader.lines() {
                if let Ok(l) = line {
                    let t = l.trim();
                    if !t.is_empty() {
                        paths.push(t.to_string());
                    }
                }
            }
            if !paths.is_empty() {
                return paths;
            }
        }
    }

    if let Ok(value) = env::var("KUKSA_VSS_PATHS") {
        let paths: Vec<String> = value
            .split(',')
            .map(str::trim)
            .filter(|path| !path.is_empty())
            .map(str::to_string)
            .collect();
        if !paths.is_empty() {
            return paths;
        }
    }

    if let Ok(content) = std::fs::read_to_string(vss_json_path()) {
        let paths = vss_leaf_paths_from_json(&content);
        if !paths.is_empty() {
            return paths;
        }
    }

    DEFAULT_VSS_PATHS.iter().map(|path| path.to_string()).collect()
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
        .unwrap_or_else(|| PathBuf::from("demo/mw_com_setup/kuksa_to_com/etc/mw_com_config.json"))
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
