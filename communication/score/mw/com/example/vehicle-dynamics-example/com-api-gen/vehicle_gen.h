/********************************************************************************
 * Copyright (c) 2025 Contributors to the Eclipse Foundation
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

#ifndef SCORE_MW_COM_EXAMPLE_VEHICLE_DYNAMICS_EXAMPLE_VEHICLE_GEN_H
#define SCORE_MW_COM_EXAMPLE_VEHICLE_DYNAMICS_EXAMPLE_VEHICLE_GEN_H

#include <cstdint>

#include "score/mw/com/types.h"

namespace score::mw::com
{

struct SpeedSample
{
    double value;
    std::uint8_t quality;
};

struct SpeedAck
{
    double value;
    std::uint8_t quality;
};

template <typename Trait>
class VehicleDynamicsService : public Trait::Base
{
  public:
    using Trait::Base::Base;

    typename Trait::template Event<SpeedSample> speed{*this, "speed"};

    typename Trait::template Event<SpeedAck> speedAck{*this, "speedAck"};
};

using VehicleDynamicsServiceProxy = AsProxy<VehicleDynamicsService>;
using VehicleDynamicsServiceSkeleton = AsSkeleton<VehicleDynamicsService>;

}  // namespace score::mw::com

#endif  // SCORE_MW_COM_EXAMPLE_VEHICLE_DYNAMICS_EXAMPLE_VEHICLE_GEN_H