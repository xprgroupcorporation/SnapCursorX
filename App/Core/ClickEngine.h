#pragma once

#ifndef NOMINMAX
#define NOMINMAX
#endif
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>

#include <atomic>
#include <array>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <thread>

#ifdef CLICKENGINE_EXPORTS
#define CLICKENGINE_API extern "C" __declspec(dllexport)
#else
#define CLICKENGINE_API extern "C" __declspec(dllimport)
#endif

typedef void (*ClickCallback)();

class ClickEngine {
public:
    ClickEngine();
    ~ClickEngine();

    void setDelayMicroseconds(std::uint64_t delayMicroseconds);
    std::uint64_t delayMicroseconds() const noexcept;
    void setTarget(int x, int y, bool followMouse, bool clickRandomness) noexcept;
    void setHoldMicroseconds(std::uint64_t holdMicroseconds) noexcept;
    void setMouseButton(int button) noexcept;

    bool start();
    void stop();
    bool isRunning() const noexcept;

private:
    void run();
    void callbackLoop();
    void waitUntil(LONGLONG targetTicks, LONGLONG intervalTicks, LONGLONG sleepThresholdTicks) const noexcept;
    void sendClick(std::uint32_t clickCount, int offsetX, int offsetY) noexcept;
    static LONG normalizeAbsoluteX(LONG x) noexcept;
    static LONG normalizeAbsoluteY(LONG y) noexcept;

    LARGE_INTEGER frequency_{};
    INPUT followClickInputs_[2]{};
    INPUT fixedClickInputs_[4]{};
    std::atomic<std::uint64_t> delayMicroseconds_{1000};
    std::atomic<double> cps_{1000.0};
    std::atomic<double> intervalSeconds_{0.001};
    std::atomic<double> baseIntervalTicksExact_{1.0};
    std::atomic<LONGLONG> intervalTicks_{1};
    std::atomic<int> targetX_{0};
    std::atomic<int> targetY_{0};
    std::atomic<std::uint64_t> holdMicroseconds_{0};
    std::atomic<int> mouseButton_{0};
    std::atomic<bool> followMouse_{true};
    std::atomic<bool> clickRandomness_{false};
    std::atomic<bool> running_{false};
    std::atomic<bool> callbackThreadRunning_{true};
    std::atomic<std::uint64_t> pendingPressCallbacks_{0};
    std::atomic<std::uint64_t> pendingReleaseCallbacks_{0};
    std::mutex callbackMutex_;
    std::condition_variable callbackCv_;
    std::thread worker_;
    std::thread callbackWorker_;
};

CLICKENGINE_API void start_clicking(int delay_us, int x, int y, bool follow_mouse, bool click_randomness);
CLICKENGINE_API void start_clicking_ex(int delay_us, int hold_us, int x, int y, bool follow_mouse, bool click_randomness, int button);
CLICKENGINE_API void stop_clicking();
CLICKENGINE_API void set_callback(ClickCallback cb);
CLICKENGINE_API void set_release_callback(ClickCallback cb);
CLICKENGINE_API std::uint64_t get_click_count();
CLICKENGINE_API bool smooth_move_cursor(int start_x, int start_y, int end_x, int end_y, int duration_ms);
CLICKENGINE_API bool mouse_button_down(int button);
CLICKENGINE_API bool mouse_button_up(int button);
CLICKENGINE_API void release_all_mouse_buttons();
