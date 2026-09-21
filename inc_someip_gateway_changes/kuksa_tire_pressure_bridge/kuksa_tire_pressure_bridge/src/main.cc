/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License Version 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

#include "kuksa_client.h"
#include "mw_com_kuksa_publisher.h"
#include "mw_com_tire_pressure_adapter.h"
#include "tire_pressure_bridge.h"

#include <csignal>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>

namespace {

volatile std::sig_atomic_t g_stop = 0;

void HandleSignal(int) {
    g_stop = 1;
}

}  // namespace

int main(int argc, char** argv) {
    std::signal(SIGINT, HandleSignal);
    std::signal(SIGTERM, HandleSignal);

    const std::string kuksa_endpoint =
        argc > 1 ? argv[1] : "127.0.0.1:55555";

    score::integration::KuksaValV1Client kuksa{kuksa_endpoint};

    if (!kuksa.Connect()) {
        return 1;
    }

    // Verify these paths against the VSS metadata loaded by your Databroker.
    score::integration::TirePressureVssPaths paths{
        .front_left =
            "Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure",
        .front_right =
            "Vehicle.Chassis.Axle.Row1.Wheel.Right.Tire.Pressure",
        .rear_left =
            "Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire.Pressure",
        .rear_right =
            "Vehicle.Chassis.Axle.Row2.Wheel.Right.Tire.Pressure",
    };

    score::integration::MwComKuksaPublisher kuksa_publisher;
    score::integration::TirePressureBridge bridge{
        kuksa,
        std::move(paths),
        [&kuksa_publisher](const score::integration::TirePressureData& data) {
            kuksa_publisher.PublishTirePressure(data);
        },
        [&kuksa_publisher](bool is_on) { kuksa_publisher.PublishHeadlight(is_on); }
    };

    score::integration::MwComTirePressureAdapter mw_com{bridge};

    if (!mw_com.Start()) {
        std::cerr << "Failed to start the mw::com tire-pressure adapter.\n";
        return 2;
    }

    if (!kuksa_publisher.Start() || !bridge.StartKuksaToMwCom()) {
        std::cerr << "Failed to start KUKSA-to-mw::com bridge.\n";
        return 3;
    }

    std::cout << "Bidirectional KUKSA/SOME-IP bridge running. Ctrl+C to stop.\n";

    while (!g_stop) {
        std::this_thread::sleep_for(std::chrono::milliseconds(250));
    }

    kuksa.Stop();
    return 0;
}
