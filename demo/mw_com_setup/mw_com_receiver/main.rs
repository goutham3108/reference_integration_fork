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

use kuksa_vehicle_gen::VehicleInterface;
use score_com::{
    Builder, FindServiceSpecifier, InstanceSpecifier, LolaRuntimeBuilderImpl, Runtime,
    RuntimeBuilder, SampleContainer, ServiceDiscovery, Subscriber, Subscription,
};
use std::env;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

const INSTANCE_SPECIFIER: &str = "/Vehicle/Service1/Instance";
const POLL_INTERVAL_MS: u64 = 200;

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

    println!("waiting for the KUKSA adapter to offer VehicleInterface...");
    let discovery = runtime.find_service::<VehicleInterface>(FindServiceSpecifier::Specific(instance));
    let consumer = loop {
        let instances = discovery
            .get_available_instances()
            .expect("failed to query available mw::com service instances");
        if let Some(builder) = instances.into_iter().next() {
            break builder.build().expect("failed to build the mw::com consumer");
        }
        thread::sleep(Duration::from_millis(POLL_INTERVAL_MS));
    };

    let vss_signal_sub = consumer
        .vss_signal
        .subscribe(16)
        .expect("failed to subscribe to VehicleInterface.vss_signal");
    println!("subscribed to VehicleInterface.vss_signal (any VSS path), waiting for samples (Ctrl+C to stop)");

    let mut vss_signal_buf = SampleContainer::new(16);
    loop {
        let received = vss_signal_sub
            .try_receive(&mut vss_signal_buf, 16)
            .expect("failed to receive vss_signal samples");
        for _ in 0..received {
            if let Some(sample) = vss_signal_buf.pop_front() {
                println!("{} = {}", sample.path_str(), sample.value_str());
            }
        }
        thread::sleep(Duration::from_millis(POLL_INTERVAL_MS));
    }
}
