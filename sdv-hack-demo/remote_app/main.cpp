// *******************************************************************************
// Copyright (c) 2026 Contributors to the Eclipse Foundation
//
// SPDX-License-Identifier: Apache-2.0
// *******************************************************************************

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include <vsomeip/vsomeip.hpp>

namespace {

constexpr vsomeip::service_t kService = 0x4301;
constexpr vsomeip::instance_t kInstance = 0x1000;
constexpr vsomeip::event_t kEvent = 0x8431;
constexpr vsomeip::eventgroup_t kEventgroup = 0x8431;

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

int main() {
    auto app = vsomeip::runtime::get()->create_application("vehicle_high_beam_remote_app");
    if (!app || !app->init()) {
        std::cerr << "Failed to initialize vehicle_high_beam_remote_app" << std::endl;
        return 1;
    }

    std::atomic<bool> offered{false};
    std::mutex offer_mutex;
    std::condition_variable offer_cv;
    app->register_state_handler([&app, &offered, &offer_cv](const vsomeip::state_type_e state) {
        if (state != vsomeip::state_type_e::ST_REGISTERED) {
            return;
        }
        const std::set<vsomeip::eventgroup_t> groups{kEventgroup};
        app->offer_event(kService, kInstance, kEvent, groups, vsomeip::event_type_e::ET_EVENT,
                         std::chrono::milliseconds::zero(), false, true);
        app->offer_service(kService, kInstance);
        offered.store(true);
        offer_cv.notify_all();
        std::cout << "Remote app offered high-beam SOME/IP service [4301.1000], event 0x8431"
                  << std::endl;
    });

    std::thread input_thread([&app, &offered, &offer_mutex, &offer_cv]() {
        std::unique_lock<std::mutex> lock{offer_mutex};
        offer_cv.wait(lock, [&offered] { return offered.load(); });
        lock.unlock();

        std::ifstream terminal_input{"/dev/tty"};
        std::istream& input_stream = terminal_input.is_open() ? static_cast<std::istream&>(terminal_input)
                                                               : std::cin;
        std::cout << "Remote input ready. Enter true or false, then press Enter." << std::endl;
        std::string input;
        while (std::getline(input_stream, input)) {
            const auto value = ParseBooleanInput(input);
            if (!value.has_value()) {
                std::cerr << "Invalid input. Enter true or false." << std::endl;
                continue;
            }
            auto payload = vsomeip::runtime::get()->create_payload();
            payload->set_data(std::vector<vsomeip::byte_t>{
                static_cast<vsomeip::byte_t>(value.value() ? 0x01U : 0x00U),
            });
            app->notify(kService, kInstance, kEvent, payload);
            std::cout << "Remote app published Vehicle.Body.Lights.Beam.High.IsOn="
                      << (value.value() ? "true" : "false") << std::endl;
        }
    });

    app->start();
    input_thread.join();
    return 0;
}
