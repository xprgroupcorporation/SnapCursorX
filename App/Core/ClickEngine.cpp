#ifndef CLICKENGINE_EXPORTS
#define CLICKENGINE_EXPORTS
#endif
#include "ClickEngine.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <mmsystem.h>
#include <mutex>
#include <random>
#include <stdexcept>
#include <thread>
#pragma comment(lib, "winmm.lib")

namespace {
constexpr LONGLONG kMicrosecondsPerSecond = 1000000LL;
constexpr LONGLONG kSleepThresholdUs = 2000;
constexpr LONGLONG kShortIntervalSleepCutoffUs = 3000;
constexpr LONGLONG kSpinThresholdUs = 250;
constexpr std::uint64_t kTimerResolution100ns = 10000;
constexpr std::uint64_t kLowMsTurboMaxDelayUs = 10000;
constexpr std::uint32_t kBatchModeClicks = 2;
constexpr double kBatchModeMinCps = 50.0;
constexpr double kTurboCompensationCapRatio = 0.20;
constexpr double kTurboPacingMultiplier = 1.15;
constexpr double kTurboGovernorCapRatio = 0.25;
constexpr double kClickRandomnessPercent = 0.10;
constexpr std::uint64_t kDebugSampleClicks = 1000;
constexpr int kLeftButton = 0;
constexpr int kRightButton = 1;
constexpr int kMiddleButton = 2;
std::atomic<ClickCallback> g_pressCallback{nullptr};
std::atomic<ClickCallback> g_releaseCallback{nullptr};
std::atomic<std::uint64_t> g_clickCount{0};
std::atomic<bool> g_abortRequested{false};

extern "C" __declspec(dllimport) long __stdcall NtSetTimerResolution(
    unsigned long DesiredResolution,
    unsigned char SetResolution,
    unsigned long* CurrentResolution);

ClickEngine& engineInstance() {
    static ClickEngine engine;
    return engine;
}

std::mutex& engineMutex() {
    static std::mutex mutex;
    return mutex;
}

LONG clampToLong(double value) noexcept {
    if (value < static_cast<double>(LONG_MIN)) {
        return LONG_MIN;
    }
    if (value > static_cast<double>(LONG_MAX)) {
        return LONG_MAX;
    }
    return static_cast<LONG>(std::lround(value));
}

int clampInt(int value, int minValue, int maxValue) noexcept {
    if (value < minValue) {
        return minValue;
    }
    if (value > maxValue) {
        return maxValue;
    }
    return value;
}

double clampDouble(double value, double minValue, double maxValue) noexcept {
    if (value < minValue) {
        return minValue;
    }
    if (value > maxValue) {
        return maxValue;
    }
    return value;
}

std::mt19937& smoothMoveRng() noexcept {
    thread_local std::mt19937 rng([] {
        const auto now = static_cast<std::uint64_t>(
            std::chrono::high_resolution_clock::now().time_since_epoch().count());
        const auto tid = static_cast<std::uint64_t>(
            std::hash<std::thread::id>{}(std::this_thread::get_id()));
        std::seed_seq seed{
            static_cast<std::uint32_t>(now & 0xFFFFFFFFULL),
            static_cast<std::uint32_t>((now >> 32) & 0xFFFFFFFFULL),
            static_cast<std::uint32_t>(tid & 0xFFFFFFFFULL),
            static_cast<std::uint32_t>((tid >> 32) & 0xFFFFFFFFULL),
            static_cast<std::uint32_t>(std::random_device{}()),
        };
        return std::mt19937(seed);
    }());
    return rng;
}

POINT bezierPoint(const POINT& p0, const POINT& p1, const POINT& p2, const POINT& p3, double t) noexcept {
    const double omt = 1.0 - t;
    const double omt2 = omt * omt;
    const double omt3 = omt2 * omt;
    const double t2 = t * t;
    const double t3 = t2 * t;
    const double x =
        (omt3 * static_cast<double>(p0.x)) +
        (3.0 * omt2 * t * static_cast<double>(p1.x)) +
        (3.0 * omt * t2 * static_cast<double>(p2.x)) +
        (t3 * static_cast<double>(p3.x));
    const double y =
        (omt3 * static_cast<double>(p0.y)) +
        (3.0 * omt2 * t * static_cast<double>(p1.y)) +
        (3.0 * omt * t2 * static_cast<double>(p2.y)) +
        (t3 * static_cast<double>(p3.y));
    POINT point{};
    point.x = clampToLong(x);
    point.y = clampToLong(y);
    return point;
}

double smoothStep(double t) noexcept {
    return t * t * (3.0 - (2.0 * t));
}

bool sendAbsoluteMove(int x, int y) noexcept {
    INPUT input{};
    input.type = INPUT_MOUSE;
    input.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;
    const LONG virtualLeft = ::GetSystemMetrics(SM_XVIRTUALSCREEN);
    const LONG virtualTop = ::GetSystemMetrics(SM_YVIRTUALSCREEN);
    const LONG virtualWidth = ::GetSystemMetrics(SM_CXVIRTUALSCREEN);
    const LONG virtualHeight = ::GetSystemMetrics(SM_CYVIRTUALSCREEN);
    input.mi.dx = (virtualWidth <= 1)
        ? 0
        : clampToLong((static_cast<double>(x - virtualLeft) * 65535.0) / static_cast<double>(virtualWidth - 1));
    input.mi.dy = (virtualHeight <= 1)
        ? 0
        : clampToLong((static_cast<double>(y - virtualTop) * 65535.0) / static_cast<double>(virtualHeight - 1));
    return ::SendInput(1, &input, sizeof(INPUT)) == 1;
}

DWORD buttonDownFlag(int button) noexcept {
    switch (button) {
    case kRightButton:
        return MOUSEEVENTF_RIGHTDOWN;
    case kMiddleButton:
        return MOUSEEVENTF_MIDDLEDOWN;
    default:
        return MOUSEEVENTF_LEFTDOWN;
    }
}

DWORD buttonUpFlag(int button) noexcept {
    switch (button) {
    case kRightButton:
        return MOUSEEVENTF_RIGHTUP;
    case kMiddleButton:
        return MOUSEEVENTF_MIDDLEUP;
    default:
        return MOUSEEVENTF_LEFTUP;
    }
}

bool sendButtonEvent(DWORD flags) noexcept {
    INPUT input{};
    input.type = INPUT_MOUSE;
    input.mi.dwFlags = flags;
    return ::SendInput(1, &input, sizeof(INPUT)) == 1;
}

void waitForTick(LONGLONG targetTick, const LARGE_INTEGER& frequency) noexcept {
    LARGE_INTEGER counter{};
    const LONGLONG sleepThresholdTicks =
        static_cast<LONGLONG>((static_cast<unsigned long long>(frequency.QuadPart) * kSleepThresholdUs) / kMicrosecondsPerSecond);
    const LONGLONG spinThresholdTicks =
        static_cast<LONGLONG>((static_cast<unsigned long long>(frequency.QuadPart) * kSpinThresholdUs) / kMicrosecondsPerSecond);

    while (!g_abortRequested.load(std::memory_order_acquire)) {
        ::QueryPerformanceCounter(&counter);
        const LONGLONG remainingTicks = targetTick - counter.QuadPart;
        if (remainingTicks <= 0) {
            return;
        }
        if (remainingTicks > sleepThresholdTicks) {
            ::Sleep(1);
            continue;
        }
        if (remainingTicks > spinThresholdTicks) {
            ::SwitchToThread();
            continue;
        }
        ::YieldProcessor();
    }
}

bool performSmoothMove(int startX, int startY, int endX, int endY, int durationMs) noexcept {
    g_abortRequested.store(false, std::memory_order_release);
    if (durationMs <= 0 || (startX == endX && startY == endY)) {
        return sendAbsoluteMove(endX, endY);
    }

    LARGE_INTEGER frequency{};
    LARGE_INTEGER startCounter{};
    if (!::QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0 || !::QueryPerformanceCounter(&startCounter)) {
        return sendAbsoluteMove(endX, endY);
    }

    const bool timerPeriodRaised = (::timeBeginPeriod(1) == TIMERR_NOERROR);
    unsigned long currentTimerResolution = 0;
    const bool ntTimerRaised =
        (NtSetTimerResolution(static_cast<unsigned long>(kTimerResolution100ns), 1, &currentTimerResolution) == 0);

    const double dx = static_cast<double>(endX - startX);
    const double dy = static_cast<double>(endY - startY);
    const double distance = std::hypot(dx, dy);
    const double durationSeconds = static_cast<double>(durationMs) / 1000.0;
    const int stepsByTime = std::max(18, durationMs / 8);
    const int stepsByDistance = std::max(18, static_cast<int>(distance / 7.0));
    const int steps = clampInt((stepsByTime > stepsByDistance) ? stepsByTime : stepsByDistance, 18, 240);

    POINT lastPoint{LONG_MIN, LONG_MIN};
    for (int index = 1; index <= steps; ++index) {
        if (g_abortRequested.load(std::memory_order_acquire)) {
            break;
        }

        const double linearT = static_cast<double>(index) / static_cast<double>(steps);
        const double motionT = smoothStep(linearT);
        POINT point{};
        point.x = clampToLong(static_cast<double>(startX) + (dx * motionT));
        point.y = clampToLong(static_cast<double>(startY) + (dy * motionT));
        if (point.x != lastPoint.x || point.y != lastPoint.y) {
            if (!sendAbsoluteMove(point.x, point.y)) {
                break;
            }
            lastPoint = point;
        }

        const double targetSeconds = durationSeconds * linearT;
        const LONGLONG targetTick =
            startCounter.QuadPart + static_cast<LONGLONG>((targetSeconds * static_cast<double>(frequency.QuadPart)) + 0.5);
        waitForTick(targetTick, frequency);
    }

    const bool completed = !g_abortRequested.load(std::memory_order_acquire);
    if (completed) {
        sendAbsoluteMove(endX, endY);
    }

    if (timerPeriodRaised) {
        ::timeEndPeriod(1);
    }
    if (ntTimerRaised) {
        NtSetTimerResolution(static_cast<unsigned long>(kTimerResolution100ns), 0, &currentTimerResolution);
    }
    return completed;
}

void waitForMicroseconds(std::uint64_t durationUs, const LARGE_INTEGER& frequency) noexcept {
    if (durationUs == 0) {
        return;
    }
    LARGE_INTEGER startCounter{};
    if (!::QueryPerformanceCounter(&startCounter)) {
        return;
    }
    const LONGLONG deltaTicks =
        static_cast<LONGLONG>((static_cast<unsigned long long>(frequency.QuadPart) * durationUs) / kMicrosecondsPerSecond);
    waitForTick(startCounter.QuadPart + std::max<LONGLONG>(1, deltaTicks), frequency);
}
}

ClickEngine::ClickEngine() {
    if (!::QueryPerformanceFrequency(&frequency_) || frequency_.QuadPart <= 0) {
        throw std::runtime_error("QueryPerformanceFrequency failed");
    }

    callbackWorker_ = std::thread(&ClickEngine::callbackLoop, this);

    followClickInputs_[0].type = INPUT_MOUSE;
    followClickInputs_[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;

    followClickInputs_[1].type = INPUT_MOUSE;
    followClickInputs_[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;

    fixedClickInputs_[0].type = INPUT_MOUSE;
    fixedClickInputs_[0].mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;

    fixedClickInputs_[1].type = INPUT_MOUSE;
    fixedClickInputs_[1].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;

    fixedClickInputs_[2].type = INPUT_MOUSE;
    fixedClickInputs_[2].mi.dwFlags = MOUSEEVENTF_LEFTUP;

    fixedClickInputs_[3].type = INPUT_MOUSE;
    fixedClickInputs_[3].mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;
}

ClickEngine::~ClickEngine() {
    stop();
    callbackThreadRunning_.store(false, std::memory_order_release);
    callbackCv_.notify_all();
    if (callbackWorker_.joinable()) {
        callbackWorker_.join();
    }
}

void ClickEngine::setDelayMicroseconds(std::uint64_t delayMicroseconds) {
    const auto normalizedDelay = delayMicroseconds == 0 ? 1ULL : delayMicroseconds;
    delayMicroseconds_.store(normalizedDelay, std::memory_order_relaxed);

    const double delayMilliseconds = static_cast<double>(normalizedDelay) / 1000.0;
    const double cps = delayMilliseconds > 0.0 ? (1000.0 / delayMilliseconds) : 1000.0;
    const double intervalSeconds = cps > 0.0 ? (1.0 / cps) : 0.001;
    cps_.store(cps, std::memory_order_relaxed);
    intervalSeconds_.store(intervalSeconds, std::memory_order_relaxed);

    const double exactTicks =
        intervalSeconds * static_cast<double>(frequency_.QuadPart);
    baseIntervalTicksExact_.store(exactTicks, std::memory_order_relaxed);

    LONGLONG intervalTicks = static_cast<LONGLONG>(exactTicks + 0.5);
    if (intervalTicks <= 0) {
        intervalTicks = 1;
    }

    intervalTicks_.store(intervalTicks, std::memory_order_relaxed);
}

std::uint64_t ClickEngine::delayMicroseconds() const noexcept {
    return delayMicroseconds_.load(std::memory_order_relaxed);
}

void ClickEngine::setTarget(int x, int y, bool followMouse, bool clickRandomness) noexcept {
    targetX_.store(x, std::memory_order_relaxed);
    targetY_.store(y, std::memory_order_relaxed);
    followMouse_.store(followMouse, std::memory_order_relaxed);
    clickRandomness_.store(clickRandomness, std::memory_order_relaxed);
}

void ClickEngine::setHoldMicroseconds(std::uint64_t holdMicroseconds) noexcept {
    holdMicroseconds_.store(holdMicroseconds, std::memory_order_relaxed);
}

void ClickEngine::setMouseButton(int button) noexcept {
    mouseButton_.store(button, std::memory_order_relaxed);
}

bool ClickEngine::start() {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true, std::memory_order_acq_rel)) {
        return false;
    }

    g_clickCount.store(0, std::memory_order_release);
    g_abortRequested.store(false, std::memory_order_release);

    try {
        worker_ = std::thread(&ClickEngine::run, this);
    } catch (...) {
        running_.store(false, std::memory_order_release);
        throw;
    }

    return true;
}

void ClickEngine::stop() {
    g_abortRequested.store(true, std::memory_order_release);
    if (!running_.exchange(false, std::memory_order_acq_rel)) {
        if (worker_.joinable()) {
            worker_.join();
        }
        return;
    }

    if (worker_.joinable()) {
        worker_.join();
    }
}

bool ClickEngine::isRunning() const noexcept {
    return running_.load(std::memory_order_acquire);
}

void ClickEngine::run() {
    ::SetThreadPriority(::GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    ::SetThreadPriorityBoost(::GetCurrentThread(), TRUE);
    const bool timerPeriodRaised = (::timeBeginPeriod(1) == TIMERR_NOERROR);
    unsigned long currentTimerResolution = 0;
    const bool ntTimerRaised =
        (NtSetTimerResolution(static_cast<unsigned long>(kTimerResolution100ns), 1, &currentTimerResolution) == 0);
    std::puts("C++ click engine started");
    ::OutputDebugStringA("C++ click engine started\n");

    LARGE_INTEGER counter{};
    ::QueryPerformanceCounter(&counter);

    const LONGLONG startTick = counter.QuadPart;
    LONGLONG nextTick = counter.QuadPart;
    const LONGLONG sleepThresholdTicks =
        static_cast<LONGLONG>((static_cast<unsigned long long>(frequency_.QuadPart) * kSleepThresholdUs) / kMicrosecondsPerSecond);
    std::mt19937 rng{std::random_device{}()};
    std::uniform_int_distribution<int> positionOffsetDist(-5, 5);
    std::uniform_real_distribution<double> delayFactorDist(1.0 - kClickRandomnessPercent, 1.0 + kClickRandomnessPercent);
    double tickError = 0.0;
    LONGLONG lastClickTick = 0;
    double debugDelayTickSum = 0.0;
    std::uint64_t debugDelaySamples = 0;
    const bool clickRandomness = clickRandomness_.load(std::memory_order_relaxed);
    const bool followMouse = followMouse_.load(std::memory_order_relaxed);
    const std::uint64_t delayUs = delayMicroseconds_.load(std::memory_order_relaxed);
    const bool pressCallbackEnabled = (g_pressCallback.load(std::memory_order_acquire) != nullptr);
    const bool releaseCallbackEnabled = (g_releaseCallback.load(std::memory_order_acquire) != nullptr);
    const bool callbackEnabled = pressCallbackEnabled || releaseCallbackEnabled;
    const std::uint64_t holdUs = holdMicroseconds_.load(std::memory_order_relaxed);
    const int mouseButton = mouseButton_.load(std::memory_order_relaxed);
    const double configuredCps =
        delayUs > 0 ? (static_cast<double>(kMicrosecondsPerSecond) / static_cast<double>(delayUs)) : 0.0;
    const std::uint32_t clicksThisCycle =
        (!clickRandomness && !callbackEnabled && holdUs == 0 && mouseButton == kLeftButton && delayUs < kLowMsTurboMaxDelayUs && configuredCps >= kBatchModeMinCps)
            ? kBatchModeClicks
            : 1U;
    double turboCompensationTicks = 0.0;
    double turboGovernorAdjustTicks = 0.0;
    double emittedClicks = 0.0;

    while (running_.load(std::memory_order_acquire)) {
        const double baseIntervalTicks = baseIntervalTicksExact_.load(std::memory_order_relaxed);
        const double randomizedIntervalTicks =
            clickRandomness ? (baseIntervalTicks * delayFactorDist(rng)) : baseIntervalTicks;
        const double cycleTicks =
            randomizedIntervalTicks * static_cast<double>(clicksThisCycle) *
            ((clicksThisCycle > 1U) ? kTurboPacingMultiplier : 1.0);
        const double turboCompensationLimit =
            (clicksThisCycle > 1U) ? (cycleTicks * kTurboCompensationCapRatio) : 0.0;
        const double appliedTurboCompensation =
            (turboCompensationTicks < turboCompensationLimit) ? turboCompensationTicks : turboCompensationLimit;
        double governorAdjustment = 0.0;
        if (clicksThisCycle > 1U) {
            const double turboGovernorLimit = cycleTicks * kTurboGovernorCapRatio;
            governorAdjustment = turboGovernorAdjustTicks;
            if (governorAdjustment > turboGovernorLimit) {
                governorAdjustment = turboGovernorLimit;
            } else if (governorAdjustment < -turboGovernorLimit) {
                governorAdjustment = -turboGovernorLimit;
            }
        }
        const double targetTicks = (cycleTicks - appliedTurboCompensation + governorAdjustment) + tickError;
        LONGLONG intervalTicks = static_cast<LONGLONG>(targetTicks);

        if (intervalTicks <= 0) {
            intervalTicks = 1;
        }
        tickError = targetTicks - static_cast<double>(intervalTicks);
        if (clicksThisCycle > 1U) {
            turboCompensationTicks -= appliedTurboCompensation;
            if (turboCompensationTicks < 0.0) {
                turboCompensationTicks = 0.0;
            }
        } else {
            turboCompensationTicks = 0.0;
        }

        nextTick += intervalTicks;
        waitUntil(nextTick, intervalTicks, sleepThresholdTicks);

        if (!running_.load(std::memory_order_acquire)) {
            break;
        }

        const int offsetX = clickRandomness ? positionOffsetDist(rng) : 0;
        const int offsetY = clickRandomness ? positionOffsetDist(rng) : 0;
        sendClick(clicksThisCycle, offsetX, offsetY);
        ::QueryPerformanceCounter(&counter);
        if (lastClickTick != 0) {
            debugDelayTickSum += static_cast<double>(counter.QuadPart - lastClickTick);
            ++debugDelaySamples;

            if (debugDelaySamples >= kDebugSampleClicks) {
                const double avgDelayMs =
                    (debugDelayTickSum * 1000.0) / (static_cast<double>(frequency_.QuadPart) * static_cast<double>(debugDelaySamples));
                std::printf("avg_delay_ms=%.4f\n", avgDelayMs);
                lastClickTick = counter.QuadPart;
                debugDelayTickSum = 0.0;
                debugDelaySamples = 0;
            } else {
                lastClickTick = counter.QuadPart;
            }
        } else {
            lastClickTick = counter.QuadPart;
        }
        emittedClicks += static_cast<double>(clicksThisCycle);
        g_clickCount.fetch_add(clicksThisCycle, std::memory_order_release);
        if (clicksThisCycle > 1U) {
            const double elapsedTicks = static_cast<double>(counter.QuadPart - startTick);
            const double idealClicksByNow =
                baseIntervalTicks > 0.0 ? (elapsedTicks / baseIntervalTicks) : emittedClicks;
            const double clickError = emittedClicks - idealClicksByNow;
            turboGovernorAdjustTicks = clickError * baseIntervalTicks;
        } else {
            turboGovernorAdjustTicks = 0.0;
        }

        if (counter.QuadPart > nextTick) {
            const LONGLONG overdueTicks = counter.QuadPart - nextTick;
            if (clicksThisCycle > 1U) {
                turboCompensationTicks += static_cast<double>(overdueTicks);
            }
            const LONGLONG skippedIntervals = overdueTicks / intervalTicks;
            if (skippedIntervals > 0) {
                nextTick += skippedIntervals * intervalTicks;
            }
        } else if (clicksThisCycle > 1U && turboCompensationTicks > 0.0) {
            const double spareTicks = static_cast<double>(nextTick - counter.QuadPart);
            turboCompensationTicks -= spareTicks;
            if (turboCompensationTicks < 0.0) {
                turboCompensationTicks = 0.0;
            }
        }
    }

    if (timerPeriodRaised) {
        ::timeEndPeriod(1);
    }
    if (ntTimerRaised) {
        NtSetTimerResolution(static_cast<unsigned long>(kTimerResolution100ns), 0, &currentTimerResolution);
    }
}

void ClickEngine::callbackLoop() {
    for (;;) {
        std::unique_lock<std::mutex> lock(callbackMutex_);
        callbackCv_.wait(lock, [this] {
            return pendingPressCallbacks_.load(std::memory_order_acquire) > 0 ||
                   pendingReleaseCallbacks_.load(std::memory_order_acquire) > 0 ||
                   !callbackThreadRunning_.load(std::memory_order_acquire);
        });

        if (!callbackThreadRunning_.load(std::memory_order_acquire) &&
            pendingPressCallbacks_.load(std::memory_order_acquire) == 0 &&
            pendingReleaseCallbacks_.load(std::memory_order_acquire) == 0) {
            break;
        }

        std::uint64_t pendingPress = pendingPressCallbacks_.exchange(0, std::memory_order_acq_rel);
        std::uint64_t pendingRelease = pendingReleaseCallbacks_.exchange(0, std::memory_order_acq_rel);
        lock.unlock();

        const auto pressCallback = g_pressCallback.load(std::memory_order_acquire);
        if (pressCallback) {
            while (pendingPress-- > 0) {
                pressCallback();
            }
        }
        const auto releaseCallback = g_releaseCallback.load(std::memory_order_acquire);
        if (releaseCallback) {
            while (pendingRelease-- > 0) {
                releaseCallback();
            }
        }
    }
}

void ClickEngine::waitUntil(LONGLONG targetTicks, LONGLONG intervalTicks, LONGLONG sleepThresholdTicks) const noexcept {
    LARGE_INTEGER counter{};
    const LONGLONG shortIntervalCutoffTicks =
        static_cast<LONGLONG>((static_cast<unsigned long long>(frequency_.QuadPart) * kShortIntervalSleepCutoffUs) / kMicrosecondsPerSecond);
    const LONGLONG spinThresholdTicks =
        static_cast<LONGLONG>((static_cast<unsigned long long>(frequency_.QuadPart) * kSpinThresholdUs) / kMicrosecondsPerSecond);
    const bool shortInterval = intervalTicks <= shortIntervalCutoffTicks;

    do {
        ::QueryPerformanceCounter(&counter);
        const LONGLONG remainingTicks = targetTicks - counter.QuadPart;
        if (remainingTicks <= 0) {
            break;
        }

        if (!shortInterval && remainingTicks > sleepThresholdTicks) {
            ::Sleep(1);
            continue;
        }

        if (remainingTicks > spinThresholdTicks) {
            ::SwitchToThread();
            continue;
        }

        ::YieldProcessor();
    } while (running_.load(std::memory_order_acquire));
}

void ClickEngine::sendClick(std::uint32_t clickCount, int offsetX, int offsetY) noexcept {
    if (clickCount == 0) {
        return;
    }

    if (followMouse_.load(std::memory_order_relaxed)) {
        const std::uint64_t holdUs = holdMicroseconds_.load(std::memory_order_relaxed);
        const int button = mouseButton_.load(std::memory_order_relaxed);
        const bool useLegacyFastLeftClick = (holdUs == 0 && button == kLeftButton && offsetX == 0 && offsetY == 0);
        if (useLegacyFastLeftClick) {
            if (clickCount == 1) {
                pendingPressCallbacks_.fetch_add(1, std::memory_order_release);
                callbackCv_.notify_one();
                ::SendInput(2, const_cast<INPUT*>(followClickInputs_), sizeof(INPUT));
                pendingReleaseCallbacks_.fetch_add(1, std::memory_order_release);
                callbackCv_.notify_one();
                return;
            }

            INPUT batchInputs[kBatchModeClicks * 2]{};
            const std::uint32_t inputCount = clickCount * 2;
            for (std::uint32_t i = 0; i < clickCount; ++i) {
                batchInputs[i * 2] = followClickInputs_[0];
                batchInputs[i * 2 + 1] = followClickInputs_[1];
            }
            pendingPressCallbacks_.fetch_add(clickCount, std::memory_order_release);
            pendingReleaseCallbacks_.fetch_add(clickCount, std::memory_order_release);
            callbackCv_.notify_one();
            ::SendInput(inputCount, batchInputs, sizeof(INPUT));
            return;
        }

        for (std::uint32_t i = 0; i < clickCount && running_.load(std::memory_order_acquire); ++i) {
            if (!sendButtonEvent(buttonDownFlag(button))) {
                return;
            }
            pendingPressCallbacks_.fetch_add(1, std::memory_order_release);
            callbackCv_.notify_one();
            waitForMicroseconds(holdUs, frequency_);
            sendButtonEvent(buttonUpFlag(button));
            pendingReleaseCallbacks_.fetch_add(1, std::memory_order_release);
            callbackCv_.notify_one();
            if (g_abortRequested.load(std::memory_order_acquire)) {
                return;
            }
        }
        return;
    }

    POINT originalCursor{};
    if (!::GetCursorPos(&originalCursor)) {
        return;
    }

    const int targetX = targetX_.load(std::memory_order_relaxed) + offsetX;
    const int targetY = targetY_.load(std::memory_order_relaxed) + offsetY;

    ::SetCursorPos(targetX, targetY);
    if (clickCount == 1) {
        ::SendInput(2, const_cast<INPUT*>(followClickInputs_), sizeof(INPUT));
    } else {
        INPUT batchInputs[kBatchModeClicks * 2]{};
        const std::uint32_t inputCount = clickCount * 2;
        for (std::uint32_t i = 0; i < clickCount; ++i) {
            batchInputs[i * 2] = followClickInputs_[0];
            batchInputs[i * 2 + 1] = followClickInputs_[1];
        }
        ::SendInput(inputCount, batchInputs, sizeof(INPUT));
    }
    ::SetCursorPos(originalCursor.x, originalCursor.y);
}

LONG ClickEngine::normalizeAbsoluteX(LONG x) noexcept {
    const LONG virtualLeft = ::GetSystemMetrics(SM_XVIRTUALSCREEN);
    const LONG virtualWidth = ::GetSystemMetrics(SM_CXVIRTUALSCREEN);
    if (virtualWidth <= 1) {
        return 0;
    }

    const double scaled = (static_cast<double>(x - virtualLeft) * 65535.0) / static_cast<double>(virtualWidth - 1);
    return static_cast<LONG>(scaled);
}

LONG ClickEngine::normalizeAbsoluteY(LONG y) noexcept {
    const LONG virtualTop = ::GetSystemMetrics(SM_YVIRTUALSCREEN);
    const LONG virtualHeight = ::GetSystemMetrics(SM_CYVIRTUALSCREEN);
    if (virtualHeight <= 1) {
        return 0;
    }

    const double scaled = (static_cast<double>(y - virtualTop) * 65535.0) / static_cast<double>(virtualHeight - 1);
    return static_cast<LONG>(scaled);
}

CLICKENGINE_API void start_clicking(int delay_us, int x, int y, bool follow_mouse, bool click_randomness) {
    start_clicking_ex(delay_us, 0, x, y, follow_mouse, click_randomness, kLeftButton);
}

CLICKENGINE_API void start_clicking_ex(int delay_us, int hold_us, int x, int y, bool follow_mouse, bool click_randomness, int button) {
    std::lock_guard<std::mutex> lock(engineMutex());

    auto& engine = engineInstance();
    g_abortRequested.store(false, std::memory_order_release);
    const auto normalizedDelay = delay_us > 0 ? static_cast<std::uint64_t>(delay_us) : 1ULL;
    const auto normalizedHold = hold_us > 0 ? static_cast<std::uint64_t>(hold_us) : 0ULL;
    engine.setTarget(x, y, follow_mouse, click_randomness);
    engine.setHoldMicroseconds(normalizedHold);
    engine.setMouseButton(button);

    if (engine.isRunning()) {
        engine.setDelayMicroseconds(normalizedDelay);
        return;
    }

    engine.setDelayMicroseconds(normalizedDelay);
    engine.start();
}

CLICKENGINE_API void stop_clicking() {
    std::lock_guard<std::mutex> lock(engineMutex());
    g_abortRequested.store(true, std::memory_order_release);
    engineInstance().stop();
}

CLICKENGINE_API void set_callback(ClickCallback cb) {
    g_pressCallback.store(cb, std::memory_order_release);
}

CLICKENGINE_API void set_release_callback(ClickCallback cb) {
    g_releaseCallback.store(cb, std::memory_order_release);
}

CLICKENGINE_API std::uint64_t get_click_count() {
    return g_clickCount.load(std::memory_order_acquire);
}

CLICKENGINE_API bool smooth_move_cursor(int start_x, int start_y, int end_x, int end_y, int duration_ms) {
    return performSmoothMove(start_x, start_y, end_x, end_y, duration_ms);
}

CLICKENGINE_API bool mouse_button_down(int button) {
    g_abortRequested.store(false, std::memory_order_release);
    return sendButtonEvent(buttonDownFlag(button));
}

CLICKENGINE_API bool mouse_button_up(int button) {
    return sendButtonEvent(buttonUpFlag(button));
}

CLICKENGINE_API void release_all_mouse_buttons() {
    sendButtonEvent(MOUSEEVENTF_LEFTUP);
    sendButtonEvent(MOUSEEVENTF_RIGHTUP);
    sendButtonEvent(MOUSEEVENTF_MIDDLEUP);
}
