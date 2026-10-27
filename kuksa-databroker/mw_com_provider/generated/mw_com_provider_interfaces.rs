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

pub mod vehicle {
    use crate::mw_com_provider_types::vehicle::{BoolSample, F32Sample, String16Sample, U8Sample};
    use score_com::{ProviderInfo, Publisher, Subscriber};

    score_com::interface!(interface BodyControlModuleService {
        Id = "BodyControlModuleService",
        horn_is_active: Event<BoolSample>,
        low_beam_is_on: Event<BoolSample>,
        high_beam_is_on: Event<BoolSample>,
        high_beam_switch_is_on: Event<BoolSample>,
        parking_lights_are_on: Event<BoolSample>,
        running_lights_are_on: Event<BoolSample>,
        front_fog_lights_are_on: Event<BoolSample>,
        rear_fog_lights_are_on: Event<BoolSample>,
        hazard_lights_are_signaling: Event<BoolSample>,
        left_indicator_is_signaling: Event<BoolSample>,
        right_indicator_is_signaling: Event<BoolSample>,
        brake_lights_are_active: Event<String16Sample>,
        hood_is_open: Event<BoolSample>,
        rear_trunk_is_open: Event<BoolSample>,
        rear_trunk_is_locked: Event<BoolSample>,
        rear_trunk_position: Event<U8Sample>,
        driver_mirror_is_folded: Event<BoolSample>,
        passenger_mirror_is_folded: Event<BoolSample>,
        driver_mirror_heating_is_on: Event<BoolSample>,
        passenger_mirror_heating_is_on: Event<BoolSample>,
        front_wiper_mode: Event<String16Sample>,
        front_wiper_intensity: Event<U8Sample>,
        front_washer_fluid_level: Event<U8Sample>,
        front_washer_fluid_is_low: Event<BoolSample>,
        rain_intensity: Event<U8Sample>,
        front_windshield_heating_is_on: Event<BoolSample>,
        rear_windshield_heating_is_on: Event<BoolSample>,
        driver_door_is_locked: Event<BoolSample>,
        driver_door_is_open: Event<BoolSample>,
        driver_door_window_position: Event<U8Sample>,
        driver_door_child_lock_is_active: Event<BoolSample>,
        front_passenger_door_is_locked: Event<BoolSample>,
        front_passenger_door_is_open: Event<BoolSample>,
        front_passenger_door_window_position: Event<U8Sample>,
        rear_driver_door_is_locked: Event<BoolSample>,
        rear_driver_door_is_open: Event<BoolSample>,
        rear_passenger_door_is_locked: Event<BoolSample>,
        rear_passenger_door_is_open: Event<BoolSample>,
        vehicle_speed: Event<F32Sample>,
    });
}
