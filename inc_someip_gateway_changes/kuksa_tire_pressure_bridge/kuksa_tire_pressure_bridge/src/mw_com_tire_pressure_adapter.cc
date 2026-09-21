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

#include "mw_com_tire_pressure_adapter.h"

#include <cstddef>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>
#include <utility>

#include "score/mw/com/runtime.h"
#include "score/mw/com/types.h"
#include "score/serializer/pre_serialized_data.h"

namespace score::integration {

namespace {

constexpr std::string_view kConfigurationPath{"score/gatewayd/etc/mw_com_config.json"};
constexpr std::string_view kTirePressureInstanceSpecifier{"gatewayd/tire_pressure"};
constexpr std::string_view kTirePressureEventName{"tire_pressure"};
constexpr std::string_view kHeadlightInstanceSpecifier{"gatewayd/headlight"};
constexpr std::string_view kHeadlightEventName{"headlight"};
constexpr std::size_t kMaxSampleCount{4U};

std::string ResolveConfigurationPath() {
    const std::string path{kConfigurationPath};
    if (std::filesystem::exists(path)) {
        return path;
    }
    for (const char* variable : {"RUNFILES_DIR", "TEST_SRCDIR"}) {
        const char* const root = std::getenv(variable);
        if (root == nullptr || root[0] == '\0') {
            continue;
        }
        const std::string candidate = std::string{root} + "/_main/" + path;
        if (std::filesystem::exists(candidate)) {
            return candidate;
        }
    }
    return path;
}

}  // namespace

struct MwComTirePressureAdapter::Impl {
    std::optional<score::mw::com::GenericProxy> tire_pressure_proxy;
    std::optional<score::mw::com::GenericProxy> headlight_proxy;
    score::mw::com::GenericProxyEvent* tire_pressure_event{nullptr};
    score::mw::com::GenericProxyEvent* headlight_event{nullptr};
};

MwComTirePressureAdapter::MwComTirePressureAdapter(
    TirePressureBridge& bridge)
    : bridge_(bridge), impl_(std::make_unique<Impl>()) {}

MwComTirePressureAdapter::~MwComTirePressureAdapter() {
    for (auto* event : {impl_->tire_pressure_event, impl_->headlight_event}) {
        if (event != nullptr) {
            (void)event->UnsetReceiveHandler();
            event->Unsubscribe();
        }
    }
}

bool MwComTirePressureAdapter::Start() {
    const std::string configuration_path = ResolveConfigurationPath();
    if (!std::filesystem::exists(configuration_path)) {
        std::cerr << "KUKSA bridge: unable to locate mw::com configuration '"
                  << configuration_path << "'.\n";
        return false;
    }

    score::mw::com::runtime::InitializeRuntime(
        score::mw::com::runtime::RuntimeConfiguration{configuration_path});
    const auto subscribe_tire_pressure = score::mw::com::GenericProxy::StartFindService(
        [this](score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
               score::mw::com::FindServiceHandle find_handle) noexcept {
            (void)score::mw::com::GenericProxy::StopFindService(find_handle);
            if (handles.empty()) {
                std::cerr << "KUKSA bridge: tire-pressure service is unavailable.\n";
                return;
            }

            auto proxy_result = score::mw::com::GenericProxy::Create(handles.front());
            if (!proxy_result.has_value()) {
                std::cerr << "KUKSA bridge: failed to create tire-pressure proxy.\n";
                return;
            }
            impl_->tire_pressure_proxy.emplace(std::move(proxy_result).value());
            auto events = impl_->tire_pressure_proxy->GetEvents();
            const auto event = events.find(kTirePressureEventName);
            if (event == events.cend()) {
                std::cerr << "KUKSA bridge: tire-pressure event is unavailable.\n";
                return;
            }

            impl_->tire_pressure_event = &event->second;
            const auto handler = impl_->tire_pressure_event->SetReceiveHandler([this]() noexcept {
                const auto samples = impl_->tire_pressure_event->GetNewSamples(
                    [this](score::mw::com::SamplePtr<void> sample) noexcept {
                        using RawSample = score::someip_gateway::serializer::PreSerializedData<0>;
                        const auto* const raw = static_cast<const RawSample*>(sample.Get());
                        if (raw == nullptr || raw->size == 0U) {
                            return;
                        }
                        const float pressure = static_cast<float>(
                            std::to_integer<unsigned char>(raw->data[raw->size - 1U]));
                        bridge_.OnMwComTirePressure(
                            {pressure, pressure, pressure, pressure});
                        std::cout << "KUKSA bridge: published tire pressure " << pressure
                                  << " to all four VSS wheel signals.\n";
                    },
                    kMaxSampleCount);
                if (!samples.has_value()) {
                    std::cerr << "KUKSA bridge: failed to read tire-pressure event samples.\n";
                }
            });
            if (!handler.has_value()) {
                std::cerr << "KUKSA bridge: failed to install tire-pressure receive handler.\n";
                return;
            }

            const auto subscription = impl_->tire_pressure_event->Subscribe(kMaxSampleCount);
            if (!subscription.has_value()) {
                std::cerr << "KUKSA bridge: failed to subscribe to tire-pressure events.\n";
                return;
            }
            std::cout << "KUKSA bridge: subscribed to gatewayd/tire_pressure.\n";
        },
        score::mw::com::InstanceSpecifier::Create(std::string{kTirePressureInstanceSpecifier}).value());
    if (!subscribe_tire_pressure.has_value()) {
        std::cerr << "KUKSA bridge: failed to start tire-pressure service discovery.\n";
        return false;
    }

    const auto subscribe_headlight = score::mw::com::GenericProxy::StartFindService(
        [this](score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
               score::mw::com::FindServiceHandle find_handle) noexcept {
            (void)score::mw::com::GenericProxy::StopFindService(find_handle);
            if (handles.empty()) {
                std::cerr << "KUKSA bridge: headlight service is unavailable.\n";
                return;
            }
            auto proxy_result = score::mw::com::GenericProxy::Create(handles.front());
            if (!proxy_result.has_value()) {
                std::cerr << "KUKSA bridge: failed to create headlight proxy.\n";
                return;
            }
            impl_->headlight_proxy.emplace(std::move(proxy_result).value());
            auto events = impl_->headlight_proxy->GetEvents();
            const auto event = events.find(kHeadlightEventName);
            if (event == events.cend()) {
                std::cerr << "KUKSA bridge: headlight event is unavailable.\n";
                return;
            }
            impl_->headlight_event = &event->second;
            const auto handler = impl_->headlight_event->SetReceiveHandler([this]() noexcept {
                const auto samples = impl_->headlight_event->GetNewSamples(
                    [this](score::mw::com::SamplePtr<void> sample) noexcept {
                        using RawSample = score::someip_gateway::serializer::PreSerializedData<0>;
                        const auto* const raw = static_cast<const RawSample*>(sample.Get());
                        if (raw == nullptr || raw->size == 0U) {
                            return;
                        }
                        const bool headlights_on = raw->data[0] != std::byte{0};
                        bridge_.OnMwComHeadlight(headlights_on);
                        std::cout << "KUKSA bridge: published headlights="
                                  << (headlights_on ? "on" : "off") << " to VSS.\n";
                    },
                    kMaxSampleCount);
                if (!samples.has_value()) {
                    std::cerr << "KUKSA bridge: failed to read headlight event samples.\n";
                }
            });
            if (!handler.has_value()) {
                std::cerr << "KUKSA bridge: failed to install headlight receive handler.\n";
                return;
            }
            const auto subscription = impl_->headlight_event->Subscribe(kMaxSampleCount);
            if (!subscription.has_value()) {
                std::cerr << "KUKSA bridge: failed to subscribe to headlight events.\n";
                return;
            }
            std::cout << "KUKSA bridge: subscribed to gatewayd/headlight.\n";
        },
        score::mw::com::InstanceSpecifier::Create(std::string{kHeadlightInstanceSpecifier}).value());
    if (!subscribe_headlight.has_value()) {
        std::cerr << "KUKSA bridge: failed to start headlight service discovery.\n";
        return false;
    }
    return true;
}

void MwComTirePressureAdapter::Publish(const TirePressureData& data) {
    (void)data;
}

}  // namespace score::integration
