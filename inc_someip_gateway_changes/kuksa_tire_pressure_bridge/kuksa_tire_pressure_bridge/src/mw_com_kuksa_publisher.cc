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

#include "mw_com_kuksa_publisher.h"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <optional>
#include <string>

#include "score/mw/com/types.h"
#include "score/serializer/pre_serialized_data.h"

namespace score::integration {

namespace {

constexpr std::string_view kTirePressureInstanceSpecifier{"kuksa/tire_pressure"};
constexpr std::string_view kTirePressureEventName{"tire_pressure"};
constexpr std::string_view kHeadlightInstanceSpecifier{"kuksa/headlight"};
constexpr std::string_view kHeadlightEventName{"headlight"};
constexpr std::size_t kTirePressurePayloadSize{4U};
constexpr std::size_t kHeadlightPayloadSize{1U};

using TirePressurePayload =
    score::someip_gateway::serializer::PreSerializedData<kTirePressurePayloadSize>;
using HeadlightPayload =
    score::someip_gateway::serializer::PreSerializedData<kHeadlightPayloadSize>;

score::mw::com::GenericSkeletonServiceElementInfo MakeServiceInfo(
    std::string_view event_name, std::size_t payload_size) {
    static std::array<score::mw::com::EventInfo, 1> tire_pressure_events{{
        {kTirePressureEventName,
         {score::someip_gateway::serializer::get_size_of_pre_serialized_data(
              kTirePressurePayloadSize),
          alignof(score::someip_gateway::serializer::PreSerializedData<0>)}},
    }};
    static std::array<score::mw::com::EventInfo, 1> headlight_events{{
        {kHeadlightEventName,
         {score::someip_gateway::serializer::get_size_of_pre_serialized_data(kHeadlightPayloadSize),
          alignof(score::someip_gateway::serializer::PreSerializedData<0>)}},
    }};

    score::mw::com::GenericSkeletonServiceElementInfo info;
    info.events = payload_size == kTirePressurePayloadSize ? tire_pressure_events : headlight_events;
    (void)event_name;
    return info;
}

std::uint8_t ToWirePressure(float pressure) {
    return static_cast<std::uint8_t>(std::clamp(std::lround(pressure), 0L, 255L));
}

}  // namespace

struct MwComKuksaPublisher::Impl {
    std::optional<score::mw::com::GenericSkeleton> tire_pressure_skeleton;
    std::optional<score::mw::com::GenericSkeleton> headlight_skeleton;
    score::mw::com::GenericSkeletonEvent* tire_pressure_event{nullptr};
    score::mw::com::GenericSkeletonEvent* headlight_event{nullptr};
};

MwComKuksaPublisher::MwComKuksaPublisher() : impl_(std::make_unique<Impl>()) {}

MwComKuksaPublisher::~MwComKuksaPublisher() {
    if (impl_->tire_pressure_skeleton.has_value()) {
        (void)impl_->tire_pressure_skeleton->StopOfferService();
    }
    if (impl_->headlight_skeleton.has_value()) {
        (void)impl_->headlight_skeleton->StopOfferService();
    }
}

bool MwComKuksaPublisher::Start() {
    const auto tire_pressure_specifier =
        score::mw::com::InstanceSpecifier::Create(std::string{kTirePressureInstanceSpecifier});
    if (!tire_pressure_specifier.has_value()) {
        return false;
    }
    auto tire_pressure_skeleton = score::mw::com::GenericSkeleton::Create(
        tire_pressure_specifier.value(),
        MakeServiceInfo(kTirePressureEventName, kTirePressurePayloadSize));
    if (!tire_pressure_skeleton.has_value()) {
        std::cerr << "KUKSA bridge: failed to create tire-pressure publisher.\n";
        return false;
    }
    impl_->tire_pressure_skeleton.emplace(std::move(tire_pressure_skeleton).value());
    auto tire_pressure_events = impl_->tire_pressure_skeleton->GetEvents();
    const auto tire_pressure_event = tire_pressure_events.find(kTirePressureEventName);
    if (tire_pressure_event == tire_pressure_events.cend()) {
        return false;
    }
    impl_->tire_pressure_event = &tire_pressure_event->second;
    if (!impl_->tire_pressure_skeleton->OfferService().has_value()) {
        std::cerr << "KUKSA bridge: failed to offer tire-pressure publisher.\n";
        return false;
    }

    const auto headlight_specifier =
        score::mw::com::InstanceSpecifier::Create(std::string{kHeadlightInstanceSpecifier});
    if (!headlight_specifier.has_value()) {
        return false;
    }
    auto headlight_skeleton = score::mw::com::GenericSkeleton::Create(
        headlight_specifier.value(), MakeServiceInfo(kHeadlightEventName, kHeadlightPayloadSize));
    if (!headlight_skeleton.has_value()) {
        std::cerr << "KUKSA bridge: failed to create headlight publisher.\n";
        return false;
    }
    impl_->headlight_skeleton.emplace(std::move(headlight_skeleton).value());
    auto headlight_events = impl_->headlight_skeleton->GetEvents();
    const auto headlight_event = headlight_events.find(kHeadlightEventName);
    if (headlight_event == headlight_events.cend()) {
        return false;
    }
    impl_->headlight_event = &headlight_event->second;
    if (!impl_->headlight_skeleton->OfferService().has_value()) {
        std::cerr << "KUKSA bridge: failed to offer headlight publisher.\n";
        return false;
    }

    std::cout << "KUKSA bridge: offered KUKSA-to-SOME/IP publishers.\n";
    return true;
}

void MwComKuksaPublisher::PublishTirePressure(const TirePressureData& data) {
    if (impl_->tire_pressure_event == nullptr) {
        return;
    }
    auto allocation = impl_->tire_pressure_event->Allocate();
    if (!allocation.has_value()) {
        return;
    }
    auto sample = std::move(allocation).value();
    auto* const payload = static_cast<TirePressurePayload*>(sample.Get());
    payload->size = kTirePressurePayloadSize;
    payload->data[0] = std::byte{ToWirePressure(data.front_left_bar)};
    payload->data[1] = std::byte{ToWirePressure(data.front_right_bar)};
    payload->data[2] = std::byte{ToWirePressure(data.rear_left_bar)};
    payload->data[3] = std::byte{ToWirePressure(data.rear_right_bar)};
    (void)impl_->tire_pressure_event->Send(std::move(sample));
    std::cout << "KUKSA bridge: forwarded tire pressure to mw::com.\n" << std::flush;
}

void MwComKuksaPublisher::PublishHeadlight(bool is_on) {
    if (impl_->headlight_event == nullptr) {
        return;
    }
    auto allocation = impl_->headlight_event->Allocate();
    if (!allocation.has_value()) {
        return;
    }
    auto sample = std::move(allocation).value();
    auto* const payload = static_cast<HeadlightPayload*>(sample.Get());
    payload->size = kHeadlightPayloadSize;
    payload->data[0] = is_on ? std::byte{1} : std::byte{0};
    (void)impl_->headlight_event->Send(std::move(sample));
    std::cout << "KUKSA bridge: forwarded headlight=" << (is_on ? "on" : "off")
              << " to mw::com.\n" << std::flush;
}

}  // namespace score::integration