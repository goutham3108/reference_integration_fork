// *******************************************************************************
// Copyright (c) 2026 Contributors to the Eclipse Foundation
//
// SPDX-License-Identifier: Apache-2.0
// *******************************************************************************

#include <array>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include "score/mw/com/runtime.h"
#include "score/mw/com/types.h"
#include "score/serializer/pre_serialized_data.h"

namespace {

constexpr std::string_view kTxInstanceSpecifier{"vehicle_high_beam/local_tx"};
constexpr std::string_view kRxInstanceSpecifier{"vehicle_high_beam/network_rx"};
constexpr std::string_view kEventName{"high_beam_state"};
constexpr std::size_t kPayloadSize{1U};
constexpr std::size_t kMaxSampleCount{4U};

using PreSerializedData = score::someip_gateway::serializer::PreSerializedData<0>;

constexpr score::mw::com::DataTypeMetaInfo kDataTypeMetaInfo{
    score::someip_gateway::serializer::get_size_of_pre_serialized_data(kPayloadSize),
    alignof(PreSerializedData)};
constexpr std::array<score::mw::com::EventInfo, 1> kEvents{{{kEventName, kDataTypeMetaInfo}}};

std::string ResolveConfigurationPath(const std::string& path) {
    if (std::filesystem::exists(path)) {
        return path;
    }
    for (const char* variable : {"TEST_SRCDIR", "RUNFILES_DIR"}) {
        const char* const root = std::getenv(variable);
        if (root == nullptr || root[0] == '\0') {
            continue;
        }
        const std::string candidate = std::string{root} + "/score_someip_gateway+/" + path;
        if (std::filesystem::exists(candidate)) {
            return candidate;
        }
    }
    return path;
}

std::optional<bool> ParseBooleanInput(const std::string& input) {
    if (input == "true") {
        return true;
    }
    if (input == "false") {
        return false;
    }
    return std::nullopt;
}

}  // namespace

class VehicleHighBeamApplication {
   public:
    explicit VehicleHighBeamApplication(std::string configuration_path)
        : configuration_path_{std::move(configuration_path)} {}

    int Run() {
        const std::string manifest = ResolveConfigurationPath(configuration_path_);
        if (!std::filesystem::exists(manifest)) {
            std::cerr << "Cannot locate mw::com configuration: " << configuration_path_ << std::endl;
            return EXIT_FAILURE;
        }
        score::mw::com::runtime::InitializeRuntime(score::mw::com::runtime::RuntimeConfiguration{manifest});
        if (!OfferLocalService() || !SubscribeToRemoteService()) {
            Cleanup();
            return EXIT_FAILURE;
        }

        std::ifstream terminal_input{"/dev/tty"};
        std::istream& input_stream = terminal_input.is_open() ? static_cast<std::istream&>(terminal_input)
                                                               : std::cin;
        std::cout << "Vehicle input ready. Enter true or false, then press Enter." << std::endl;
        std::string input;
        while (std::getline(input_stream, input)) {
            const auto value = ParseBooleanInput(input);
            if (!value.has_value()) {
                std::cerr << "Invalid input. Enter true or false." << std::endl;
                continue;
            }
            PublishLocalState(value.value());
        }
        Cleanup();
        return EXIT_SUCCESS;
    }

   private:
    bool OfferLocalService() {
        const auto instance = score::mw::com::InstanceSpecifier::Create(std::string{kTxInstanceSpecifier});
        if (!instance.has_value()) {
            return false;
        }
        score::mw::com::GenericSkeletonServiceElementInfo create_params;
        create_params.events = kEvents;
        auto skeleton_result = score::mw::com::GenericSkeleton::Create(instance.value(), create_params);
        if (!skeleton_result.has_value()) {
            return false;
        }
        tx_skeleton_.emplace(std::move(skeleton_result).value());
        if (!tx_skeleton_->OfferService().has_value()) {
            return false;
        }
        auto events = tx_skeleton_->GetEvents();
        const auto event = events.find(kEventName);
        if (event == events.cend()) {
            return false;
        }
        tx_event_ = &event->second;
        return true;
    }

    bool SubscribeToRemoteService() {
        const auto instance = score::mw::com::InstanceSpecifier::Create(std::string{kRxInstanceSpecifier});
        if (!instance.has_value()) {
            return false;
        }
        const auto result = score::mw::com::GenericProxy::StartFindService(
            [this](score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
                   score::mw::com::FindServiceHandle handle) noexcept {
                OnRemoteServiceAvailable(std::move(handles), handle);
            },
            instance.value());
        return result.has_value();
    }

    void PublishLocalState(const bool value) {
        if (tx_event_ == nullptr) {
            std::cerr << "Vehicle Tx service is unavailable" << std::endl;
            return;
        }
        auto sample_result = tx_event_->Allocate();
        if (!sample_result.has_value()) {
            std::cerr << "Cannot allocate Vehicle high-beam sample" << std::endl;
            return;
        }
        auto sample = std::move(sample_result).value();
        auto* const data = static_cast<PreSerializedData*>(sample.Get());
        data->size = kPayloadSize;
        data->data[0] = value ? std::byte{0x01} : std::byte{0x00};
        if (!tx_event_->Send(std::move(sample)).has_value()) {
            std::cerr << "Cannot publish Vehicle high-beam state" << std::endl;
            return;
        }
        std::cout << "Vehicle app published Vehicle.Body.Lights.Beam.High.IsOn="
                  << (value ? "true" : "false") << std::endl;
    }

    void OnRemoteServiceAvailable(
        score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
        score::mw::com::FindServiceHandle handle) noexcept {
        (void)score::mw::com::GenericProxy::StopFindService(handle);
        if (handles.empty()) {
            return;
        }
        auto proxy_result = score::mw::com::GenericProxy::Create(handles.front());
        if (!proxy_result.has_value()) {
            return;
        }
        rx_proxy_.emplace(std::move(proxy_result).value());
        auto events = rx_proxy_->GetEvents();
        const auto event = events.find(kEventName);
        if (event == events.cend()) {
            return;
        }
        rx_event_ = &event->second;
        if (!rx_event_->SetReceiveHandler([this]() noexcept { OnRemoteState(); }).has_value() ||
            !rx_event_->Subscribe(kMaxSampleCount).has_value()) {
            std::cerr << "Cannot subscribe to remote high-beam updates" << std::endl;
            return;
        }
        std::cout << "Vehicle app subscribed to remote high-beam updates." << std::endl;
    }

    void OnRemoteState() noexcept {
        const auto samples = rx_event_->GetNewSamples(
            [](score::mw::com::SamplePtr<void> sample) noexcept {
                const auto* const data = static_cast<const PreSerializedData*>(sample.Get());
                if (data == nullptr || data->size != kPayloadSize ||
                    (data->data[0] != std::byte{0x00} && data->data[0] != std::byte{0x01})) {
                    std::cerr << "Invalid remote high-beam payload" << std::endl;
                    return;
                }
                std::cout << "Vehicle app received Vehicle.Body.Lights.Beam.High.IsOn="
                          << (data->data[0] == std::byte{0x01} ? "true" : "false") << std::endl;
            },
            kMaxSampleCount);
        if (!samples.has_value()) {
            std::cerr << "Cannot retrieve remote high-beam samples" << std::endl;
        }
    }

    void Cleanup() noexcept {
        if (rx_event_ != nullptr) {
            (void)rx_event_->UnsetReceiveHandler();
            rx_event_->Unsubscribe();
        }
        if (tx_skeleton_.has_value()) {
            tx_skeleton_->StopOfferService();
        }
    }

    std::string configuration_path_;
    std::optional<score::mw::com::GenericSkeleton> tx_skeleton_;
    std::optional<score::mw::com::GenericProxy> rx_proxy_;
    score::mw::com::GenericSkeletonEvent* tx_event_{nullptr};
    score::mw::com::GenericProxyEvent* rx_event_{nullptr};
};

int main(int argc, char* argv[]) {
    std::string configuration_path{"score/gatewayd/etc/mw_com_config.json"};
    for (int index = 1; index + 1 < argc; ++index) {
        if (std::string_view{argv[index]} == "--configuration") {
            configuration_path = argv[++index];
        }
    }
    return VehicleHighBeamApplication{std::move(configuration_path)}.Run();
}
