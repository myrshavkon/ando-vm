
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/android/binder.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define DEVICE "/dev/binderfs/binder"
#define MAP_SIZE (1024 * 1024)
#define READ_SIZE 4096

static void fail(const char *message)
{
    fprintf(stderr, "ERROR: %s: %s\n", message, strerror(errno));
    exit(EXIT_FAILURE);
}

static int open_binder(void **mapping)
{
    int fd = open(DEVICE, O_RDWR | O_CLOEXEC);
    if (fd < 0)
        fail("Cannot open Binder device");

    struct binder_version version = {0};
    if (ioctl(fd, BINDER_VERSION, &version) < 0)
        fail("BINDER_VERSION failed");

    printf("Binder protocol version: %d\n", version.protocol_version);

    if (version.protocol_version != BINDER_CURRENT_PROTOCOL_VERSION) {
        fprintf(stderr, "Unexpected Binder protocol version\n");
        exit(EXIT_FAILURE);
    }

    *mapping = mmap(NULL, MAP_SIZE, PROT_READ, MAP_PRIVATE, fd, 0);
    if (*mapping == MAP_FAILED)
        fail("Binder mmap failed");

    return fd;
}

static void write_command(int fd, const void *command, size_t size)
{
    struct binder_write_read bwr = {
        .write_size = size,
        .write_buffer = (binder_uintptr_t)(uintptr_t)command
    };

    if (ioctl(fd, BINDER_WRITE_READ, &bwr) < 0)
        fail("BINDER_WRITE_READ write failed");

    if (bwr.write_consumed != size) {
        fprintf(stderr, "Incomplete Binder write: %zu of %zu bytes\n",
                (size_t)bwr.write_consumed, size);
        exit(EXIT_FAILURE);
    }
}

static size_t read_commands(int fd, void *buffer, size_t capacity)
{
    struct binder_write_read bwr = {
        .read_size = capacity,
        .read_buffer = (binder_uintptr_t)(uintptr_t)buffer
    };

    if (ioctl(fd, BINDER_WRITE_READ, &bwr) < 0)
        fail("BINDER_WRITE_READ read failed");

    return (size_t)bwr.read_consumed;
}

static void free_transaction_buffer(int fd, binder_uintptr_t address)
{
    struct {
        uint32_t command;
        binder_uintptr_t buffer;
    } __attribute__((packed)) request = {
        .command = BC_FREE_BUFFER,
        .buffer = address
    };

    write_command(fd, &request, sizeof(request));
}

static int run_server(void)
{
    void *mapping;
    int fd = open_binder(&mapping);

    if (ioctl(fd, BINDER_SET_CONTEXT_MGR, NULL) < 0)
        fail("Could not become Binder context manager");

    uint32_t enter_looper = BC_ENTER_LOOPER;
    write_command(fd, &enter_looper, sizeof(enter_looper));

    puts("READY");
    fflush(stdout);

    uint8_t buffer[READ_SIZE];

    for (;;) {
        size_t used = read_commands(fd, buffer, sizeof(buffer));
        size_t offset = 0;

        while (offset + sizeof(uint32_t) <= used) {
            uint32_t command;
            memcpy(&command, buffer + offset, sizeof(command));
            offset += sizeof(command);

            if (command == BR_NOOP || command == BR_TRANSACTION_COMPLETE)
                continue;

            if (command == BR_TRANSACTION) {
                struct binder_transaction_data transaction;

                if (offset + sizeof(transaction) > used) {
                    fprintf(stderr, "Incomplete BR_TRANSACTION\n");
                    return EXIT_FAILURE;
                }

                memcpy(&transaction, buffer + offset, sizeof(transaction));
                offset += sizeof(transaction);

                const char expected[] = "ping";
                const char *message =
                    (const char *)(uintptr_t)transaction.data.ptr.buffer;

                if (transaction.data_size != sizeof(expected) ||
                    memcmp(message, expected, sizeof(expected)) != 0) {
                    fprintf(stderr, "Server received an unexpected message\n");
                    return EXIT_FAILURE;
                }

                puts("Server received: ping");

                static const char reply[] = "pong";

                struct {
                    uint32_t command;
                    struct binder_transaction_data transaction;
                } __attribute__((packed)) response = {
                    .command = BC_REPLY,
                    .transaction = {
                        .target.ptr = 0,
                        .cookie = 0,
                        .code = transaction.code,
                        .flags = 0,
                        .data_size = sizeof(reply),
                        .offsets_size = 0,
                        .data.ptr = {
                            .buffer = (binder_uintptr_t)(uintptr_t)reply,
                            .offsets = 0
                        }
                    }
                };

                write_command(fd, &response, sizeof(response));
                free_transaction_buffer(fd, transaction.data.ptr.buffer);

                puts("Server sent: pong");

                munmap(mapping, MAP_SIZE);
                close(fd);
                return EXIT_SUCCESS;
            }

            if (command == BR_ERROR) {
                int32_t error_code;
                if (offset + sizeof(error_code) > used)
                    return EXIT_FAILURE;

                memcpy(&error_code, buffer + offset, sizeof(error_code));
                fprintf(stderr, "Binder server error: %d\n", error_code);
                return EXIT_FAILURE;
            }

            fprintf(stderr, "Unexpected Binder server command: 0x%x\n",
                    command);
            return EXIT_FAILURE;
        }
    }
}

static int run_client(void)
{
    void *mapping;
    int fd = open_binder(&mapping);

    static const char message[] = "ping";

    struct {
        uint32_t command;
        struct binder_transaction_data transaction;
    } __attribute__((packed)) request = {
        .command = BC_TRANSACTION,
        .transaction = {
            .target.handle = 0,
            .cookie = 0,
            .code = 1,
            .flags = 0,
            .data_size = sizeof(message),
            .offsets_size = 0,
            .data.ptr = {
                .buffer = (binder_uintptr_t)(uintptr_t)message,
                .offsets = 0
            }
        }
    };

    write_command(fd, &request, sizeof(request));
    puts("Client sent: ping");

    uint8_t buffer[READ_SIZE];

    for (;;) {
        size_t used = read_commands(fd, buffer, sizeof(buffer));
        size_t offset = 0;

        while (offset + sizeof(uint32_t) <= used) {
            uint32_t command;
            memcpy(&command, buffer + offset, sizeof(command));
            offset += sizeof(command);

            if (command == BR_TRANSACTION_COMPLETE || command == BR_NOOP)
                continue;

            if (command == BR_REPLY) {
                struct binder_transaction_data reply;

                if (offset + sizeof(reply) > used) {
                    fprintf(stderr, "Incomplete BR_REPLY\n");
                    return EXIT_FAILURE;
                }

                memcpy(&reply, buffer + offset, sizeof(reply));
                offset += sizeof(reply);

                const char expected[] = "pong";
                const char *received =
                    (const char *)(uintptr_t)reply.data.ptr.buffer;

                if (reply.data_size != sizeof(expected) ||
                    memcmp(received, expected, sizeof(expected)) != 0) {
                    fprintf(stderr, "Client received an unexpected reply\n");
                    return EXIT_FAILURE;
                }

                puts("Client received: pong");
                free_transaction_buffer(fd, reply.data.ptr.buffer);

                munmap(mapping, MAP_SIZE);
                close(fd);

                puts("PASS: Binder IPC transaction completed successfully");
                return EXIT_SUCCESS;
            }

            if (command == BR_DEAD_REPLY) {
                fprintf(stderr, "Binder server died before replying\n");
                return EXIT_FAILURE;
            }

            if (command == BR_ERROR) {
                int32_t error_code;
                if (offset + sizeof(error_code) > used)
                    return EXIT_FAILURE;

                memcpy(&error_code, buffer + offset, sizeof(error_code));
                fprintf(stderr, "Binder client error: %d\n", error_code);
                return EXIT_FAILURE;
            }

            fprintf(stderr, "Unexpected Binder client command: 0x%x\n",
                    command);
            return EXIT_FAILURE;
        }
    }
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s server|client\n", argv[0]);
        return EXIT_FAILURE;
    }

    if (strcmp(argv[1], "server") == 0)
        return run_server();

    if (strcmp(argv[1], "client") == 0)
        return run_client();

    fprintf(stderr, "Unknown mode: %s\n", argv[1]);
    return EXIT_FAILURE;
}
