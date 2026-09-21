#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <memory>
#include <set>
#include <thread>
#include <vsomeip/vsomeip.hpp>

namespace {

constexpr vsomeip::service_t kService = 0x4100;
constexpr vsomeip::instance_t kInstance = 0x1000;
constexpr vsomeip::event_t kEvent = 0x8410;
constexpr vsomeip::eventgroup_t kEventgroup = 0x8410;

}  // namespace

int main() {
    auto app = vsomeip::runtime::get()->create_application("tire_pressure_publisher");
    if (!app || !app->init()) {
        std::cerr << "Failed to initialize tire_pressure_publisher" << std::endl;
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
        std::cout << "Offering service [4100.1000], event 0x8410" << std::endl;
    });

    app->register_subscription_handler(
        kService, kInstance, kEventgroup,
        [](vsomeip::service_t service, vsomeip::instance_t instance,
           vsomeip::eventgroup_t eventgroup, bool subscribed) {
            std::cout << "Subscription update service=0x" << std::hex << std::setw(4)
                      << std::setfill('0') << service << " instance=0x" << std::setw(4) << instance
                      << " eventgroup=0x" << std::setw(4) << eventgroup << std::dec
                      << " subscribed=" << (subscribed ? "true" : "false") << std::endl;
            return true;
        });

    std::thread sender([&app]() {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        std::uint8_t pressure = 40;
        while (true) {
            auto payload = vsomeip::runtime::get()->create_payload();
            std::vector<vsomeip::byte_t> data{0x00, 0x04, 0x00, 0x00, 0x00, pressure};
            payload->set_data(data);
            app->notify(kService, kInstance, kEvent, payload);
            std::cout << "NOTIFY [4100.1000.8410] pressure=" << static_cast<int>(pressure)
                      << " payload=00 04 00 00 00 " << std::hex << std::setw(2) << std::setfill('0')
                      << static_cast<int>(pressure) << std::dec << std::endl;

            pressure = (pressure <= 20) ? 40 : static_cast<std::uint8_t>(pressure - 1);
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    });

    app->start();
    sender.join();
    return 0;
}
