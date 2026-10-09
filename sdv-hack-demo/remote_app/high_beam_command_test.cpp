#include "high_beam_udp_protocol.h"

int main() {
    using high_beam_udp::CommandResult;
    high_beam_udp::Frame frame{17152, 4096, 33840, 1, {1}};
    unsigned int writes = 0;
    bool output = false;
    const auto write = [&](bool value) { ++writes; output = value; return true; };
    if (high_beam_udp::ApplyCommand(frame, true, write) != CommandResult::kApplied || !output || writes != 1) {
        return 1;
    }
    frame.payload[0] = 0;
    if (high_beam_udp::ApplyCommand(frame, true, write) != CommandResult::kApplied || output) {
        return 2;
    }
    const auto previous_writes = writes;
    frame.payload[0] = 1;
    if (high_beam_udp::ApplyCommand(frame, false, write) != CommandResult::kDisplayed || writes != previous_writes) {
        return 3;
    }
    if (high_beam_udp::ApplyCommand(frame, true, [](bool) { return false; }) != CommandResult::kOutputFailed) {
        return 4;
    }
    for (const unsigned char size : {0, 2, 32}) {
        frame.payload_size = size;
        if (high_beam_udp::ApplyCommand(frame, true, write) != CommandResult::kMalformed) { return 5; }
    }
    frame.payload_size = 1;
    frame.payload[0] = 2;
    if (high_beam_udp::ApplyCommand(frame, true, write) != CommandResult::kMalformed || writes != previous_writes) {
        return 6;
    }
    if (high_beam_udp::FeedbackFrame(frame, 4097, 33843).has_value()) {
        return 7;
    }
    for (const std::uint16_t event : {33840, 33842}) {
        for (const bool value : {true, false}) {
            frame.event = event;
            frame.payload[0] = static_cast<std::uint8_t>(value);
            const auto feedback = high_beam_udp::FeedbackFrame(frame, 4097, event + 1);
            if (!feedback || feedback->instance != 4097 || feedback->event != event + 1 ||
                high_beam_udp::BooleanValue(*feedback) != value) {
                return 8;
            }
            const auto bytes = high_beam_udp::Encode(*feedback);
            const auto decoded = high_beam_udp::Decode(bytes.data(), bytes.size());
            if (!decoded || decoded->event != event + 1 || high_beam_udp::BooleanValue(*decoded) != value) {
                return 9;
            }
        }
    }
    return 0;
}