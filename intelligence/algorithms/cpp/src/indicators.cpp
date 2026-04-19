/**
 * cpp/src/indicators.cpp
 * ======================
 * C++ pybind11 extension: stockindicators
 *
 * Implements RSI, MACD, and Bollinger Bands to match the pandas reference
 * in tools/yfinance_fetcher_pure.py within ±0.01 absolute tolerance.
 *
 * Algorithmic notes (matching pandas exactly):
 *   RSI   — EWM with com=(period-1), adjust=True (pandas default)
 *   MACD  — EWM with span=n, adjust=False (explicitly set in Python)
 *   BB    — rolling mean + rolling std (ddof=1, pandas default)
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace py = pybind11;
using namespace pybind11::literals;

static const double kNaN = std::numeric_limits<double>::quiet_NaN();

// ---------------------------------------------------------------------------
// EWM helpers
// ---------------------------------------------------------------------------

/**
 * adjust=True EWM (pandas default for RSI avg_gain/avg_loss).
 * Recursive equivalent:
 *   num[t] = x[t] + (1-alpha)*num[t-1]
 *   den[t] = 1    + (1-alpha)*den[t-1]
 *   ewm[t] = num[t] / den[t]
 * NaN values propagate the decay without contributing to the weighted sum.
 */
static std::vector<double> ewm_adjusted(const std::vector<double>& x, double alpha) {
    std::vector<double> out(x.size(), kNaN);
    double num = 0.0, den = 0.0;
    double one_minus = 1.0 - alpha;
    bool started = false;
    for (size_t i = 0; i < x.size(); ++i) {
        if (std::isnan(x[i])) {
            if (started) {
                num *= one_minus;
                den *= one_minus;
            }
            out[i] = kNaN;
        } else {
            if (!started) {
                num = x[i];
                den = 1.0;
                started = true;
            } else {
                num = x[i] + one_minus * num;
                den = 1.0  + one_minus * den;
            }
            out[i] = num / den;
        }
    }
    return out;
}

/**
 * adjust=False EWM (used for MACD lines in the Python reference).
 *   ewm[t] = alpha*x[t] + (1-alpha)*ewm[t-1]
 * Initialised with the first non-NaN observation (same as pandas).
 */
static std::vector<double> ewm_unadjusted(const std::vector<double>& x, double alpha) {
    std::vector<double> out(x.size(), kNaN);
    double ewm = kNaN;
    double one_minus = 1.0 - alpha;
    for (size_t i = 0; i < x.size(); ++i) {
        if (!std::isnan(x[i])) {
            if (std::isnan(ewm)) {
                ewm = x[i];
            } else {
                ewm = alpha * x[i] + one_minus * ewm;
            }
            out[i] = ewm;
        }
    }
    return out;
}

// ---------------------------------------------------------------------------
// compute_rsi
// ---------------------------------------------------------------------------

/**
 * RSI using EWM with com=(period-1), adjust=True, min_periods=period.
 * Returns 50.0 when there is insufficient data.
 */
static double compute_rsi(const std::vector<double>& prices, int period = 14) {
    int n = static_cast<int>(prices.size());
    if (n < period + 1) return 50.0;

    // Differences (gain / loss split), index 0 is NaN (no prior value)
    std::vector<double> gain(n, kNaN);
    std::vector<double> loss(n, kNaN);
    for (int i = 1; i < n; ++i) {
        double d = prices[i] - prices[i - 1];
        gain[i] = d > 0.0 ? d : 0.0;
        loss[i] = d < 0.0 ? -d : 0.0;
    }

    // alpha = 1 / (1 + com) = 1 / period
    double alpha = 1.0 / static_cast<double>(period);
    auto avg_gain = ewm_adjusted(gain, alpha);
    auto avg_loss = ewm_adjusted(loss, alpha);

    // Last valid pair (both non-NaN)
    double last_gain = kNaN, last_loss = kNaN;
    for (int i = n - 1; i >= 0; --i) {
        if (!std::isnan(avg_gain[i]) && !std::isnan(avg_loss[i])) {
            last_gain = avg_gain[i];
            last_loss = avg_loss[i];
            break;
        }
    }

    if (std::isnan(last_gain)) return 50.0;
    if (last_loss == 0.0) return 100.0;

    double rs = last_gain / last_loss;
    return 100.0 - (100.0 / (1.0 + rs));
}

// ---------------------------------------------------------------------------
// compute_macd
// ---------------------------------------------------------------------------

static py::dict compute_macd(
    const std::vector<double>& prices,
    int fast   = 12,
    int slow   = 26,
    int signal = 9)
{
    int n = static_cast<int>(prices.size());
    if (n < slow + signal) {
        return py::dict(
            "macd"_a=0.0, "signal"_a=0.0,
            "histogram"_a=0.0, "bullish_crossover"_a=false);
    }

    // MACD uses adjust=False EWM (explicit in Python reference)
    double alpha_fast   = 2.0 / (fast   + 1.0);
    double alpha_slow   = 2.0 / (slow   + 1.0);
    double alpha_signal = 2.0 / (signal + 1.0);

    auto ema_fast = ewm_unadjusted(prices, alpha_fast);
    auto ema_slow = ewm_unadjusted(prices, alpha_slow);

    // MACD line = fast EMA − slow EMA
    std::vector<double> macd_line(n, kNaN);
    for (int i = 0; i < n; ++i) {
        if (!std::isnan(ema_fast[i]) && !std::isnan(ema_slow[i])) {
            macd_line[i] = ema_fast[i] - ema_slow[i];
        }
    }

    // Signal line = EWM(MACD line, adjust=False)
    auto sig_line = ewm_unadjusted(macd_line, alpha_signal);

    // Collect the last two valid (macd, signal) pairs for crossover check
    double last_macd = kNaN, last_sig = kNaN;
    double prev_macd = kNaN, prev_sig = kNaN;
    for (int i = n - 1; i >= 0; --i) {
        if (!std::isnan(macd_line[i]) && !std::isnan(sig_line[i])) {
            if (std::isnan(last_macd)) {
                last_macd = macd_line[i];
                last_sig  = sig_line[i];
            } else {
                prev_macd = macd_line[i];
                prev_sig  = sig_line[i];
                break;
            }
        }
    }

    double histogram = last_macd - last_sig;
    bool bullish_crossover =
        !std::isnan(prev_macd) &&
        (last_macd > last_sig) && (prev_macd <= prev_sig);

    auto r4 = [](double v) { return std::round(v * 1e4) / 1e4; };

    return py::dict(
        "macd"_a            = r4(last_macd),
        "signal"_a          = r4(last_sig),
        "histogram"_a       = r4(histogram),
        "bullish_crossover"_a = bullish_crossover);
}

// ---------------------------------------------------------------------------
// compute_bollinger_bands
// ---------------------------------------------------------------------------

static py::dict compute_bollinger_bands(
    const std::vector<double>& prices,
    int    period  = 20,
    double std_dev = 2.0)
{
    int n = static_cast<int>(prices.size());
    if (n < period) {
        return py::dict(
            "upper"_a=0.0, "middle"_a=0.0, "lower"_a=0.0,
            "pct_b"_a=0.5);
    }

    // Rolling window ending at the last price (ddof=1, matching pandas)
    int start = n - period;
    double sum   = 0.0;
    double sum_sq = 0.0;
    for (int i = start; i < n; ++i) {
        sum    += prices[i];
        sum_sq += prices[i] * prices[i];
    }
    double mean     = sum / period;
    double variance = (sum_sq - static_cast<double>(period) * mean * mean)
                      / (period - 1);
    double std_val  = std::sqrt(variance < 0.0 ? 0.0 : variance);

    double upper   = mean + std_dev * std_val;
    double lower   = mean - std_dev * std_val;
    double current = prices.back();
    double width   = upper - lower;
    double pct_b   = (width != 0.0) ? (current - lower) / width : 0.5;

    auto r2 = [](double v) { return std::round(v * 1e2) / 1e2; };
    auto r4 = [](double v) { return std::round(v * 1e4) / 1e4; };

    return py::dict(
        "upper"_a  = r2(upper),
        "middle"_a = r2(mean),
        "lower"_a  = r2(lower),
        "pct_b"_a  = r4(pct_b));
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

PYBIND11_MODULE(stockindicators, m) {
    m.doc() = "C++ technical indicator extension for StockAgent (Phase 1)";

    m.def("compute_rsi",
          &compute_rsi,
          py::arg("prices"),
          py::arg("period") = 14,
          "RSI via EWM(com=period-1, adjust=True). Returns float in [0,100].");

    m.def("compute_macd",
          &compute_macd,
          py::arg("prices"),
          py::arg("fast")   = 12,
          py::arg("slow")   = 26,
          py::arg("signal") = 9,
          "MACD/Signal/Histogram via EWM(adjust=False). Returns dict.");

    m.def("compute_bollinger_bands",
          &compute_bollinger_bands,
          py::arg("prices"),
          py::arg("period")  = 20,
          py::arg("std_dev") = 2.0,
          "Bollinger Bands via rolling mean+std (ddof=1). Returns dict.");
}
