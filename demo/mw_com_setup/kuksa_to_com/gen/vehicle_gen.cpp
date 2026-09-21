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

#include "vehicle_gen.h"
#include "score/mw/com/rust/score_com_cpp_bridge/register_interface.h"

BEGIN_EXPORT_MW_COM_INTERFACE(VehicleInterface, ::score::mw::com::VehicleProxy, ::score::mw::com::VehicleSkeleton)
EXPORT_MW_COM_EVENT(::score::mw::com::VssSignal, vss_signal)
END_EXPORT_MW_COM_INTERFACE()

EXPORT_MW_COM_TYPE(VssSignal, ::score::mw::com::VssSignal)
