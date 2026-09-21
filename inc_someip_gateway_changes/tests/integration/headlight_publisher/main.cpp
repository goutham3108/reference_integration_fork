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

#include <chrono>
#include <cstdint>
#include <iostream>
#include <set>
#include <thread>
#include <vector>

#include <vsomeip/vsomeip.hpp>

namespace {

constexpr vsomeip::service_t kService = 0x4200;
constexpr vsomeip::instance_t kInstance = 0x1001;
constexpr vsomeip::event_t kEvent = 0x8420;
constexpr vsomeip::eventgroup_t kEventgroup = 0x8420;

}  // namespace

int main() {
    auto app = vsomeip::runtime::get()->create_application("headlight_publisher");
    if (!app || !app->init()) {
        std::cerr << "Failed to initialize headlight_publisher" << std::endl;
        return 1;
    }

    app->register_state_handler([&app](vsomeip::state_type_e state) {
        if (state != vsomeip::state_type_e::ST_REGISTERED) {
            return;
        }

        std::set<vsomeip::eventgroup_t> groups{kEventgroup};
        app->offer_event(kService, kInstance, kEvent, groups, vsomeip::event_type_e::ET_EVENT,
                         std::chrono::milliseconds::zero(), false, true);
        app->offer_service(kService, kInstance);
        std::cout << "Offering headlight service [4200.1001], event 0x8420" << std::endl;
    });

    std::thread sender([&app]() {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        bool headlights_on = true;
        while (true) {
            auto payload = vsomeip::runtime::get()->create_payload();
            payload->set_data(std::vector<vsomeip::byte_t>{static_cast<vsomeip::byte_t>(headlights_on)});
            app->notify(kService, kInstance, kEvent, payload);
            std::cout << "NOTIFY [4200.1001.8420] headlights="
                      << (headlights_on ? "on" : "off") << std::endl;
            headlights_on = !headlights_on;
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    });

    app->start();
    sender.join();
    return 0;
}
