// This file is a copy of inc_someip_gateway/tests/integration/vehicle_high_beam_remote_app/main.cpp
// It is packaged here so the demo is self-contained under sdv-hack-demo.

#include <algorithm>
#include <atomic>
#include <array>
#include <cerrno>
#include <csignal>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <fcntl.h>
#include <linux/gpio.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <poll.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>
#include <vsomeip/vsomeip.hpp>

#include <kvsbuilder.hpp>
#include "high_beam_udp_protocol.h"
#include "sdv-hack-demo/include/speed_payload.h"
#include "score/mw/lifecycle/report_running.h"
#include "score/mw/log/logging.h"

namespace {

std::atomic<bool> running{true};
static_assert(std::atomic<bool>::is_always_lock_free);

void StopRemote(int) {
    running.store(false);
}

bool ReadInputLine(std::istream& stream, int fd, std::string& line) {
    while (running.load()) {
        pollfd descriptor{fd, POLLIN, 0};
        const int result = poll(&descriptor, 1, 100);
        if (result < 0 && errno != EINTR) {
            return false;
        }
        if (result > 0) {
            return static_cast<bool>(std::getline(stream, line));
        }
    }
    return false;
}

constexpr auto kPublishPeriod = std::chrono::seconds{2};
constexpr auto kGpioSamplePeriod = std::chrono::milliseconds{5};
constexpr auto kGpioDebouncePeriod = std::chrono::milliseconds{30};
constexpr char kSensorStateKey[] = "high_beam_state";
constexpr std::uint16_t kDefaultBridgePort = 35000U;
constexpr std::uint16_t kDefaultRemotePort = 35001U;

struct Route {
    std::string name;
    std::uint16_t service;
    std::uint16_t vehicle_instance;
    std::uint16_t remote_instance;
    std::uint16_t vehicle_event;
    std::uint16_t remote_event;
};

std::optional<bool> ParseBooleanInput(const std::string& input) {
    if (input == "true") {
        return true;
    }
    if (input == "false") {
        return false;
    }
    return std::nullopt;
}

std::optional<double> ParseSpeedInput(const std::string& input) {
    try {
        std::size_t parsed = 0U;
        const double value = std::stod(input, &parsed);
        if (parsed != input.size()) {
            return std::nullopt;
        }
        return value;
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

void PrintRemoteMenu() {
    std::cout << "\nRemote menu\n"
              << "1  High-beam (true/false)\n"
              << "2  Vehicle.speed (number)\n"
              << "q  Quit remote app\n"
              << "Select: " << std::flush;
}

std::uint16_t ResolvePort(const char* name, const std::uint16_t fallback) {
    const char* value = std::getenv(name);
    return value == nullptr ? fallback : static_cast<std::uint16_t>(std::stoi(value));
}

std::string DetectGpioChip() {
    for (unsigned int index = 0U; index < 64U; ++index) {
        const std::string path = "/dev/gpiochip" + std::to_string(index);
        const int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
        if (fd < 0) {
            continue;
        }

        gpiochip_info info{};
        const bool found = ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &info) == 0 &&
                   (std::strncmp(info.name, "pinctrl-", 8U) == 0 ||
                    std::strncmp(info.label, "pinctrl-", 8U) == 0);
        close(fd);
        if (found) {
            return path;
        }
    }
    return "/dev/gpiochip0";
}

int OpenGpioInput() {
    const char* const configured_chip = std::getenv("HIGH_BEAM_GPIO_CHIP");
    const std::string chip_path = configured_chip == nullptr || configured_chip[0] == '\0'
                                      ? DetectGpioChip()
                                      : configured_chip;
    const char* const configured_line = std::getenv("HIGH_BEAM_GPIO_LINE");
    unsigned long line = 17UL;
    if (configured_line != nullptr && configured_line[0] != '\0') {
        char* end = nullptr;
        errno = 0;
        line = std::strtoul(configured_line, &end, 10);
        if (errno != 0 || end == configured_line || *end != '\0' || line > UINT32_MAX) {
            score::mw::log::LogError() << "Invalid HIGH_BEAM_GPIO_LINE: " << configured_line;
            return -1;
        }
    }

    const int chip_fd = open(chip_path.c_str(), O_RDONLY | O_CLOEXEC);
    if (chip_fd < 0) {
        score::mw::log::LogError() << "Cannot open GPIO chip " << chip_path << ": "
                                  << std::strerror(errno);
        return -1;
    }

    gpiohandle_request request{};
    request.lineoffsets[0] = static_cast<std::uint32_t>(line);
    request.flags = GPIOHANDLE_REQUEST_INPUT | GPIOHANDLE_REQUEST_BIAS_PULL_UP;
    request.lines = 1U;
    std::strncpy(request.consumer_label, "sdv-remote-highbeam", sizeof(request.consumer_label) - 1U);
    const int result = ioctl(chip_fd, GPIO_GET_LINEHANDLE_IOCTL, &request);
    const int request_error = errno;
    close(chip_fd);
    if (result < 0) {
        score::mw::log::LogError() << "Cannot request BCM GPIO " << line << " with pull-up: "
                                  << std::strerror(request_error);
        return -1;
    }
    score::mw::log::LogWarn() << "Using GPIO controller " << chip_path << " line " << line;
    return request.fd;
}

bool ReadGpioHigh(const int gpio_fd, bool& high) {
    gpiohandle_data values{};
    if (ioctl(gpio_fd, GPIOHANDLE_GET_LINE_VALUES_IOCTL, &values) < 0) {
        score::mw::log::LogError() << "Cannot read high-beam GPIO: " << std::strerror(errno);
        return false;
    }
    high = values.values[0] != 0U;
    return true;
}

class GpioOutput {
 public:
    ~GpioOutput() {
        if (fd_ >= 0) {
            (void)Write(false);
            close(fd_);
        }
    }

    bool Open() {
        const char* configured_chip = std::getenv("HIGH_BEAM_GPIO_OUTPUT_CHIP");
        const char* input_chip = std::getenv("HIGH_BEAM_GPIO_CHIP");
        const std::string input_path = input_chip == nullptr || input_chip[0] == '\0'
            ? DetectGpioChip() : input_chip;
        const std::string chip = configured_chip == nullptr || configured_chip[0] == '\0'
            ? input_path : configured_chip;
        try {
            const char* configured_line = std::getenv("HIGH_BEAM_GPIO_OUTPUT_LINE");
            const std::string text = configured_line == nullptr ? "27" : configured_line;
            std::size_t parsed = 0;
            const auto line = std::stoul(text, &parsed);
            if (parsed != text.size() || line > UINT32_MAX || text.front() == '-') {
                throw std::invalid_argument("invalid output line");
            }
            line_ = static_cast<std::uint32_t>(line);
            const char* input_line = std::getenv("HIGH_BEAM_GPIO_LINE");
            const auto input_offset = input_line == nullptr ? 17UL : std::stoul(input_line);
            if (chip == input_path && line_ == input_offset) {
                score::mw::log::LogError() << "GPIO input and output must use different lines";
                return false;
            }
        } catch (const std::exception& error) {
            score::mw::log::LogError() << "Invalid GPIO output configuration: " << std::string{error.what()};
            return false;
        }
        const int chip_fd = open(chip.c_str(), O_RDONLY | O_CLOEXEC);
        if (chip_fd < 0) {
            score::mw::log::LogError() << "Cannot open GPIO output chip " << chip;
            return false;
        }
        gpiohandle_request request{};
        request.lineoffsets[0] = line_;
        request.flags = GPIOHANDLE_REQUEST_OUTPUT;
        request.lines = 1;
        std::strncpy(request.consumer_label, "sdv-highbeam-output", sizeof(request.consumer_label) - 1);
        const int result = ioctl(chip_fd, GPIO_GET_LINEHANDLE_IOCTL, &request);
        const int error = errno;
        close(chip_fd);
        if (result < 0) {
            score::mw::log::LogError() << "Cannot request GPIO output: " << std::string{std::strerror(error)};
            return false;
        }
        fd_ = request.fd;
        score::mw::log::LogWarn() << "Remote LED initialized OFF: " << chip << " line " << line_;
        return true;
    }

    bool Write(bool value) {
        gpiohandle_data data{};
        data.values[0] = value ? 1 : 0;
        if (ioctl(fd_, GPIOHANDLE_SET_LINE_VALUES_IOCTL, &data) < 0) {
            score::mw::log::LogError() << "GPIO output write failed: " << std::string{std::strerror(errno)};
            return false;
        }
        score::mw::log::LogWarn() << "Remote GPIO output applied Low.IsOn=" << value << " line " << line_;
        return true;
    }

 private:
    int fd_{-1};
    std::uint32_t line_{27};
};

void SetOutboundState(const bool value, std::atomic<bool>& outbound_state,
                      const std::shared_ptr<score::mw::per::kvs::Kvs>& sensor_store,
                      const char* source, std::condition_variable& outbound_changed,
                      std::mutex& outbound_mutex, std::uint64_t& outbound_generation) {
    std::unique_lock<std::mutex> lock{outbound_mutex};
    const bool previous = outbound_state.exchange(value);
    if (previous == value) {
        return;
    }
    (void)sensor_store->set_value(kSensorStateKey, score::mw::per::kvs::KvsValue{value});
    (void)sensor_store->flush();
    score::mw::log::LogWarn() << "Remote " << source << " input set High.IsOn="
                              << (value ? "true" : "false");
    ++outbound_generation;
    lock.unlock();
    outbound_changed.notify_one();
}

void MonitorGpio(const int gpio_fd, bool line_high, std::atomic<bool>& outbound_state,
                 const std::shared_ptr<score::mw::per::kvs::Kvs>& sensor_store,
                 std::condition_variable& outbound_changed, std::mutex& outbound_mutex,
                 std::uint64_t& outbound_generation) {
    bool candidate_pressed = !line_high;
    bool stable_pressed = candidate_pressed;
    auto candidate_since = std::chrono::steady_clock::now();
    while (running.load()) {
        std::this_thread::sleep_for(kGpioSamplePeriod);
        if (!ReadGpioHigh(gpio_fd, line_high)) {
            running.store(false);
            break;
        }
        const bool pressed = !line_high;
        if (pressed != candidate_pressed) {
            candidate_pressed = pressed;
            candidate_since = std::chrono::steady_clock::now();
        } else if (candidate_pressed != stable_pressed &&
                   std::chrono::steady_clock::now() - candidate_since >= kGpioDebouncePeriod) {
            stable_pressed = candidate_pressed;
            SetOutboundState(stable_pressed, outbound_state, sensor_store, "GPIO BCM 17",
                             outbound_changed, outbound_mutex, outbound_generation);
        }
    }
    close(gpio_fd);
}

std::string ResolveAddress(const char* name, const char* fallback) {
    const char* value = std::getenv(name);
    return value == nullptr || value[0] == '\0' ? fallback : value;
}

bool SetAddress(sockaddr_in& address, const std::string& value) {
    return inet_pton(AF_INET, value.c_str(), &address.sin_addr) == 1;
}

std::optional<std::vector<Route>> LoadRoutes() {
    const char* const configured = std::getenv("SIGNAL_ROUTE_CONFIG");
    const std::string path = configured == nullptr || configured[0] == '\0' ? "signal_routes.json" : configured;
    std::ifstream input{path};
    if (!input.is_open()) {
        score::mw::log::LogError() << "Cannot open signal route configuration";
        return std::nullopt;
    }
    try {
        const auto document = nlohmann::json::parse(input);
        std::vector<Route> routes;
        for (const auto& item : document.at("routes")) {
            routes.push_back(Route{item.at("name").get<std::string>(), item.at("service").get<std::uint16_t>(),
                                   item.at("vehicleInstance").get<std::uint16_t>(),
                                   item.at("remoteInstance").get<std::uint16_t>(),
                                   item.at("vehicleEvent").get<std::uint16_t>(),
                                   item.at("remoteEvent").get<std::uint16_t>()});
        }
        return routes;
    } catch (const std::exception& error) {
        score::mw::log::LogError() << "Invalid signal route configuration: " << error.what();
        return std::nullopt;
    }
}

int CreateUdpSocket(const std::uint16_t port, const std::string& bind_ip) {
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (socket_fd < 0) {
        return -1;
    }
    sockaddr_in address{};
    address.sin_family = AF_INET;
    if (!SetAddress(address, bind_ip)) {
        close(socket_fd);
        return -1;
    }
    address.sin_port = htons(port);
    if (bind(socket_fd, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0) {
        close(socket_fd);
        return -1;
    }
    return socket_fd;
}

}  // namespace

int main() {
    std::signal(SIGINT, StopRemote);
    std::signal(SIGTERM, StopRemote);
    const auto routes = LoadRoutes();
    if (!routes.has_value() || routes->empty()) {
        return 1;
    }
    const auto high_beam = std::find_if(routes->begin(), routes->end(), [](const Route& route) {
        return route.name == "high_beam";
    });
    if (high_beam == routes->end()) {
        score::mw::log::LogError() << "Route configuration has no high_beam route";
        return 1;
    }
    const auto low_beam = std::find_if(routes->begin(), routes->end(), [](const Route& route) {
        return route.name == "low_beam";
    });
    if (low_beam == routes->end()) {
        score::mw::log::LogError() << "Route configuration has no low_beam route";
        return 1;
    }
    const char* const configured_kvs_dir = std::getenv("HIGH_BEAM_KVS_DIR");
    const std::string kvs_dir = configured_kvs_dir != nullptr && configured_kvs_dir[0] != '\0'
                                    ? configured_kvs_dir
                                    : "/tmp/score_high_beam_sensor";
    std::error_code filesystem_error;
    std::filesystem::create_directories(kvs_dir, filesystem_error);
    if (filesystem_error) {
        score::mw::log::LogError() << "Cannot create sensor KVS directory: " << kvs_dir;
        return 1;
    }
    score::mw::per::kvs::KvsBuilder kvs_builder{score::mw::per::kvs::InstanceId{1U}};
    kvs_builder.dir(std::string{kvs_dir});
    auto kvs_result = kvs_builder.build();
    if (!kvs_result.has_value()) {
        score::mw::log::LogError() << "Cannot open sensor KVS in " << kvs_dir;
        return 1;
    }
    auto sensor_store = std::make_shared<score::mw::per::kvs::Kvs>(std::move(kvs_result).value());
    std::atomic<bool> outbound_state{false};
    std::atomic<bool> low_beam_state{false};
    std::condition_variable outbound_changed;
    std::mutex outbound_mutex;
    std::mutex publish_mutex;
    std::uint64_t outbound_generation{0U};

    const std::uint16_t bridge_port = ResolvePort("HIGH_BEAM_BRIDGE_UDP_PORT", kDefaultBridgePort);
    const std::uint16_t remote_port = ResolvePort("HIGH_BEAM_REMOTE_UDP_PORT", kDefaultRemotePort);
    const std::string bind_ip = ResolveAddress("HIGH_BEAM_BIND_IP", "0.0.0.0");
    const std::string bridge_ip = ResolveAddress("HIGH_BEAM_BRIDGE_IP", "127.0.0.1");
    const int udp_socket = CreateUdpSocket(remote_port, bind_ip);
    if (udp_socket < 0) {
        score::mw::log::LogError() << "Failed to bind remote UDP port " << remote_port;
        return 1;
    }
    timeval receive_timeout{0, 200000};
    if (setsockopt(udp_socket, SOL_SOCKET, SO_RCVTIMEO, &receive_timeout, sizeof(receive_timeout)) < 0) {
        close(udp_socket);
        return 1;
    }
    sockaddr_in bridge_address{};
    bridge_address.sin_family = AF_INET;
    if (!SetAddress(bridge_address, bridge_ip)) {
        score::mw::log::LogError() << "Invalid HIGH_BEAM_BRIDGE_IP: " << bridge_ip;
        close(udp_socket);
        return 1;
    }
    bridge_address.sin_port = htons(bridge_port);
    if (std::getenv("PROCESSIDENTIFIER") != nullptr) {
        score::mw::lifecycle::report_running();
    }

    const char* const configured_input = std::getenv("HIGH_BEAM_INPUT");
    const std::string input_mode = configured_input == nullptr || configured_input[0] == '\0'
                                       ? "gpio"
                                       : configured_input;
    const bool hardware = input_mode == "gpio";
    std::thread gpio_thread;
    GpioOutput led;
    if (hardware) {
        if (!led.Open()) {
            close(udp_socket);
            return 1;
        }
        const int gpio_fd = OpenGpioInput();
        if (gpio_fd < 0) {
            close(udp_socket);
            return 1;
        }
        bool initial_line_high = true;
        if (!ReadGpioHigh(gpio_fd, initial_line_high)) {
            close(gpio_fd);
            close(udp_socket);
            return 1;
        }
        SetOutboundState(!initial_line_high, outbound_state, sensor_store, "GPIO BCM 17",
                         outbound_changed, outbound_mutex, outbound_generation);
        score::mw::log::LogWarn() << "Remote GPIO initialized once; switch monitoring and LED output remain active";
        gpio_thread = std::thread([gpio_fd, initial_line_high, &outbound_state, &sensor_store, &outbound_changed,
                                    &outbound_mutex, &outbound_generation]() {
            MonitorGpio(gpio_fd, initial_line_high, outbound_state, sensor_store, outbound_changed, outbound_mutex,
                        outbound_generation);
        });
    } else if (input_mode != "menu") {
        score::mw::log::LogError() << "Invalid HIGH_BEAM_INPUT mode: " << input_mode
                                  << " (choose 'gpio' or 'menu')";
        close(udp_socket);
        return 1;
    }
    std::thread input_thread([&outbound_state, &sensor_store, &routes, &bridge_address, udp_socket, hardware,
                                    &outbound_changed, &outbound_mutex, &outbound_generation]() {
            std::ifstream terminal_input{"/dev/tty"};
            const int terminal_fd = terminal_input.is_open() ? open("/dev/tty", O_RDONLY | O_CLOEXEC) : -1;
            const int input_fd = terminal_fd >= 0 ? terminal_fd : STDIN_FILENO;
            std::istream& input_stream = terminal_input.is_open()
                                             ? static_cast<std::istream&>(terminal_input)
                                             : std::cin;
            PrintRemoteMenu();
            std::string input;
            while (ReadInputLine(input_stream, input_fd, input)) {
                if (input == "q") {
                    running.store(false);
                    break;
                }
                if (input == "1") {
                    std::cout << "High-beam value (true/false): " << std::flush;
                    if (!ReadInputLine(input_stream, input_fd, input)) {
                        break;
                    }
                    const auto value = ParseBooleanInput(input);
                    if (!value.has_value()) {
                        score::mw::log::LogWarn() << "Invalid high-beam input. Enter true or false.";
                        continue;
                    }
                    SetOutboundState(value.value(), outbound_state, sensor_store, "menu", outbound_changed,
                                     outbound_mutex, outbound_generation);
                    PrintRemoteMenu();
                    continue;
                }
                if (input == "2") {
                    const auto dynamics = std::find_if(routes->begin(), routes->end(), [](const Route& route) {
                        return route.name == "vehicle_dynamics";
                    });
                    if (dynamics == routes->end()) {
                        score::mw::log::LogError() << "Route configuration has no vehicle_dynamics route";
                        continue;
                    }
                    std::cout << "Vehicle.speed value: " << std::flush;
                    if (!ReadInputLine(input_stream, input_fd, input)) {
                        break;
                    }
                    const auto speed = ParseSpeedInput(input);
                    if (!speed.has_value()) {
                        score::mw::log::LogWarn() << "Invalid speed input. Enter a number.";
                        continue;
                    }
                    high_beam_udp::Frame frame{dynamics->service, dynamics->remote_instance,
                                               dynamics->remote_event, 9U, {}};
                    vehicle_dynamics_wire::EncodeSpeed(speed.value(), 3U, frame.payload.data());
                    const auto encoded = high_beam_udp::Encode(frame);
                    (void)sendto(udp_socket, encoded.data(), encoded.size(), 0,
                                 reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
                    score::mw::log::LogWarn() << "Remote published Vehicle.speed=" << speed.value();
                    PrintRemoteMenu();
                    continue;
                }
                score::mw::log::LogWarn() << "Invalid menu option. Select 1, 2, or q.";
            }
            if (terminal_fd >= 0) {
                close(terminal_fd);
            }
            if (!hardware) {
                running.store(false);
            }
        });
    std::thread receive_thread([udp_socket, &routes, &bridge_address, &led, &input_mode,
                               &outbound_state, &low_beam_state, &sensor_store, &outbound_changed,
                               &outbound_mutex, &outbound_generation, &publish_mutex]() {
        std::array<std::uint8_t, high_beam_udp::kFrameSize> bytes{};
        while (running.load()) {
            sockaddr_in sender{};
            socklen_t sender_size = sizeof(sender);
            const auto received = recvfrom(udp_socket, bytes.data(), bytes.size(), 0,
                                           reinterpret_cast<sockaddr*>(&sender), &sender_size);
            if (received <= 0) {
                continue;
            }
            const auto frame = high_beam_udp::Decode(bytes.data(), static_cast<std::size_t>(received));
            const auto route = frame.has_value()
                                   ? std::find_if(routes->begin(), routes->end(), [&frame](const Route& candidate) {
                                         return frame->service == candidate.service &&
                                                frame->instance == candidate.vehicle_instance &&
                                                frame->event == candidate.vehicle_event;
                                     })
                                   : routes->end();
            if (!frame.has_value() || route == routes->end()) {
                score::mw::log::LogError() << "Remote app received invalid UDP SOME/IP frame";
                continue;
            }
            char sender_ip[INET_ADDRSTRLEN]{};
            const char* const sender_address =
                inet_ntop(AF_INET, &sender.sin_addr, sender_ip, sizeof(sender_ip));
            if (route->name != "high_beam" && route->name != "low_beam") {
                if (frame->payload_size == sizeof(double) + 1U) {
                    const double received_value = vehicle_dynamics_wire::DecodeSpeed(frame->payload.data());
                    score::mw::log::LogWarn() << "Remote received Vehicle.speed=" << received_value
                                              << " from "
                                              << (sender_address == nullptr ? "<unknown>" : sender_address)
                                              << ":" << ntohs(sender.sin_port);
                } else {
                    score::mw::log::LogWarn() << "Remote received " << route->name
                                              << " payload_size=" << frame->payload_size;
                }
                high_beam_udp::Frame acknowledgement{route->service, route->remote_instance,
                                                      route->remote_event, frame->payload_size, frame->payload};
                const auto encoded = high_beam_udp::Encode(acknowledgement);
                (void)sendto(udp_socket, encoded.data(), encoded.size(), 0,
                             reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
                if (frame->payload_size == sizeof(double) + 1U) {
                    const double acked_value = vehicle_dynamics_wire::DecodeSpeed(frame->payload.data());
                    score::mw::log::LogWarn() << "Remote forwarded Vehicle.speed=" << acked_value;
                } else {
                    score::mw::log::LogWarn() << "Remote acknowledged " << route->name
                                              << " payload_size=" << frame->payload_size;
                }
                continue;
            }
            const auto value = high_beam_udp::BooleanValue(*frame);
            if (!value.has_value()) {
                score::mw::log::LogError() << "Remote rejected malformed lighting command";
                continue;
            }
            std::lock_guard<std::mutex> publish_lock{publish_mutex};
            if (route->name == "high_beam") {
                score::mw::log::LogWarn() << "Remote received vehicle-side command High.IsOn=" << *value;
                SetOutboundState(*value, outbound_state, sensor_store, "KUKSA command", outbound_changed,
                                 outbound_mutex, outbound_generation);
            } else {
                score::mw::log::LogWarn() << "Remote received vehicle-side command Low.IsOn=" << *value;
                const auto result = high_beam_udp::ApplyCommand(*frame, input_mode == "gpio", [&led](bool state) {
                    return led.Write(state);
                });
                if (result == high_beam_udp::CommandResult::kOutputFailed) {
                    running.store(false);
                    continue;
                }
                low_beam_state.store(*value);
            }
            const auto feedback = high_beam_udp::FeedbackFrame(*frame, route->remote_instance, route->remote_event);
            const auto encoded = high_beam_udp::Encode(*feedback);
            (void)sendto(udp_socket, encoded.data(), encoded.size(), 0,
                         reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
            score::mw::log::LogWarn() << "Remote published feedback " << route->name << "=" << *value;
        }
    });

    std::uint64_t last_sent_generation = std::numeric_limits<std::uint64_t>::max();
    auto next_publish = std::chrono::steady_clock::now();
    while (running.load()) {
        {
            std::unique_lock<std::mutex> lock{outbound_mutex};
            outbound_changed.wait_for(lock, std::chrono::milliseconds{100}, [&]() {
                return outbound_generation != last_sent_generation;
            });
            if (!running.load()) {
                break;
            }
            if (outbound_generation == last_sent_generation && std::chrono::steady_clock::now() < next_publish) {
                continue;
            }
            last_sent_generation = outbound_generation;
        }
        std::lock_guard<std::mutex> publish_lock{publish_mutex};
        const bool value = outbound_state.load();
        high_beam_udp::Frame outbound{high_beam->service, high_beam->remote_instance,
                          high_beam->remote_event, 1U,
                          {static_cast<std::uint8_t>(value)}};
        const auto frame = high_beam_udp::Encode(outbound);
        (void)sendto(udp_socket, frame.data(), frame.size(), 0,
                     reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
        high_beam_udp::Frame low_feedback{low_beam->service, low_beam->remote_instance,
                         low_beam->remote_event, 1U,
                         {static_cast<std::uint8_t>(low_beam_state.load())}};
        const auto low_frame = high_beam_udp::Encode(low_feedback);
        (void)sendto(udp_socket, low_frame.data(), low_frame.size(), 0,
                 reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
        next_publish = std::chrono::steady_clock::now() + kPublishPeriod;
    }
    input_thread.join();
    if (gpio_thread.joinable()) {
        gpio_thread.join();
    }
    receive_thread.join();
    if (!hardware || led.Write(false)) {
        high_beam_udp::Frame low_feedback{low_beam->service, low_beam->remote_instance,
                                         low_beam->remote_event, 1U, {0}};
        const auto bytes = high_beam_udp::Encode(low_feedback);
        (void)sendto(udp_socket, bytes.data(), bytes.size(), 0,
                     reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
    }
    close(udp_socket);
    return 0;
}
