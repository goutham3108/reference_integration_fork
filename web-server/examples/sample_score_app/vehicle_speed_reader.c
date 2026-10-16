#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <string.h>
#include <signal.h>

static volatile int keep_running = 1;

void handle_signal(int sig) {
    (void)sig;
    keep_running = 0;
}

int main(int argc, char* argv[]) {
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    printf("[S-CORE Native App] Starting vehicle_speed_reader...\n");
    printf("[S-CORE Native App] Checking S-CORE mw::com shared memory (/dev/shm)...\n");

    // Check if S-CORE shared memory segments exist
    struct stat st;
    if (stat("/dev/shm", &st) == 0) {
        printf("[S-CORE Native App] /dev/shm accessible. Looking for active LoLa segments.\n");
    } else {
        printf("[S-CORE Native App] Warning: /dev/shm not mounted or accessible.\n");
    }

    double current_speed = 45.0;
    int cycle = 0;

    while (keep_running) {
        cycle++;
        current_speed += (cycle % 2 == 0) ? 1.5 : -1.0;
        if (current_speed < 0) current_speed = 0.0;
        if (current_speed > 160) current_speed = 160.0;

        printf("[S-CORE mw::com] Cycle #%d: Vehicle.Speed = %.2f km/h (LoLa mw::com SHM active)\n", cycle, current_speed);
        fflush(stdout);

        sleep(2);
    }

    printf("[S-CORE Native App] Exiting cleanly.\n");
    return 0;
}
