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

#include "tire_pressure_bridge.h"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <utility>

namespace score::integration {

namespace {

constexpr std::string_view kHeadlightVssPath{"Vehicle.Body.Lights.Beam.High.IsOn"};

bool PublishPressure(IKuksaClient& kuksa, std::string_view signal_path, float pressure_kpa) {
    if (pressure_kpa < 0.0F ||
        pressure_kpa > static_cast<float>(std::numeric_limits<std::uint16_t>::max())) {
        std::cerr << "TirePressureBridge: tire pressure is outside the uint16 VSS range.\n";
        return false;
    }
    return kuksa.PublishUint16(signal_path, static_cast<std::uint16_t>(std::lround(pressure_kpa)));
}

}  // namespace

TirePressureBridge::TirePressureBridge(
    IKuksaClient& kuksa,
    TirePressureVssPaths paths,
        MwComPublishCallback mw_com_publish,
        MwComHeadlightPublishCallback mw_com_headlight_publish)
    : kuksa_(kuksa),
      paths_(std::move(paths)),
            mw_com_publish_(std::move(mw_com_publish)),
            mw_com_headlight_publish_(std::move(mw_com_headlight_publish)) {}

void TirePressureBridge::OnMwComTirePressure(
    const TirePressureData& data) {

    bool ok = true;

    ok &= PublishPressure(kuksa_, paths_.front_left, data.front_left_bar);
    ok &= PublishPressure(kuksa_, paths_.front_right, data.front_right_bar);
    ok &= PublishPressure(kuksa_, paths_.rear_left, data.rear_left_bar);
    ok &= PublishPressure(kuksa_, paths_.rear_right, data.rear_right_bar);

    if (!ok) {
        std::cerr << "TirePressureBridge: one or more KUKSA writes failed\n";
    }
}

void TirePressureBridge::OnMwComHeadlight(bool is_on) {
    if (!kuksa_.PublishBool(kHeadlightVssPath, is_on)) {
        std::cerr << "TirePressureBridge: failed to publish headlight state\n";
    }
}

bool TirePressureBridge::StartKuksaToMwCom() {
    if (!mw_com_publish_ || !mw_com_headlight_publish_) {
        std::cerr << "TirePressureBridge: reverse mw::com publisher is not configured\n";
        return false;
    }

    bool ok = true;

    ok &= kuksa_.SubscribeFloat(
        paths_.front_left,
        [this](float value) {
            latest_.front_left_bar = value;
            PublishAggregateToMwCom();
        });

    ok &= kuksa_.SubscribeFloat(
        paths_.front_right,
        [this](float value) {
            latest_.front_right_bar = value;
            PublishAggregateToMwCom();
        });

    ok &= kuksa_.SubscribeFloat(
        paths_.rear_left,
        [this](float value) {
            latest_.rear_left_bar = value;
            PublishAggregateToMwCom();
        });

    ok &= kuksa_.SubscribeFloat(
        paths_.rear_right,
        [this](float value) {
            latest_.rear_right_bar = value;
            PublishAggregateToMwCom();
        });

    ok &= kuksa_.SubscribeBool(
        std::string{kHeadlightVssPath},
        [this](bool value) { mw_com_headlight_publish_(value); });

    return ok;
}

void TirePressureBridge::PublishAggregateToMwCom() {
    if (mw_com_publish_) {
        mw_com_publish_(latest_);
    }
}

}  // namespace score::integration
