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

#pragma once

#include "tire_pressure_bridge.h"

#include <memory>

namespace score::integration {

class MwComTirePressureAdapter final {
public:
    explicit MwComTirePressureAdapter(TirePressureBridge& bridge);
    ~MwComTirePressureAdapter();

    // Discover/start the generated mw::com proxy and subscribe to its
    // TirePressure event.
    bool Start();

    // Optional reverse path. Convert TirePressureData to the generated
    // mw::com event/sample type and publish it.
    void Publish(const TirePressureData& data);

private:
    struct Impl;

    TirePressureBridge& bridge_;
    std::unique_ptr<Impl> impl_;
};

}  // namespace score::integration
