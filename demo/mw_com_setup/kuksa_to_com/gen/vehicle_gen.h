/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

#ifndef SHOWCASES_KUKSA_TO_COM_GEN_VEHICLE_GEN_H
#define SHOWCASES_KUKSA_TO_COM_GEN_VEHICLE_GEN_H

#include <cstddef>
#include <cstdint>

#include "score/mw/com/types.h"

namespace score::mw::com
{

// A generic carrier for any KUKSA VSS signal, read via the databroker CLI.
// path/value are UTF-8 text truncated to their buffer size; *_len holds the
// actual byte length. This lets the producer forward any VSS path (not a
// fixed set) without changing the interface.
inline constexpr std::size_t kVssMaxPathLen = 160;
inline constexpr std::size_t kVssMaxValueLen = 128;

struct VssSignal
{
    std::uint8_t path[kVssMaxPathLen];
    std::uint16_t path_len;
    std::uint8_t value[kVssMaxValueLen];
    std::uint16_t value_len;
};

template <typename Trait>
class VehicleInterface : public Trait::Base
{
  public:
    using Trait::Base::Base;
    typename Trait::template Event<VssSignal> vss_signal{*this, "vss_signal"};
};

using VehicleProxy = AsProxy<VehicleInterface>;
using VehicleSkeleton = AsSkeleton<VehicleInterface>;

}  // namespace score::mw::com

#endif  // SHOWCASES_KUKSA_TO_COM_GEN_VEHICLE_GEN_H
