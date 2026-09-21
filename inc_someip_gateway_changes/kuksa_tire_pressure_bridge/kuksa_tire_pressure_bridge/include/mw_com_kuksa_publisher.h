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

#ifndef KUKSA_TIRE_PRESSURE_BRIDGE_KUKSA_TIRE_PRESSURE_BRIDGE_INCLUDE_MW_COM_KUKSA_PUBLISHER
#define KUKSA_TIRE_PRESSURE_BRIDGE_KUKSA_TIRE_PRESSURE_BRIDGE_INCLUDE_MW_COM_KUKSA_PUBLISHER


#include "tire_pressure_types.h"

#include <memory>

namespace score::integration {

class MwComKuksaPublisher final {
public:
    MwComKuksaPublisher();
    ~MwComKuksaPublisher();

    bool Start();
    void PublishTirePressure(const TirePressureData& data);
    void PublishHeadlight(bool is_on);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace score::integration


#endif // KUKSA_TIRE_PRESSURE_BRIDGE_KUKSA_TIRE_PRESSURE_BRIDGE_INCLUDE_MW_COM_KUKSA_PUBLISHER
