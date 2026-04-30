cmake_minimum_required(VERSION 3.18)
project(stockindicators CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# pybind11 — fetched from GitHub so no local install is required
# ---------------------------------------------------------------------------
include(FetchContent)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.13.6
)
FetchContent_MakeAvailable(pybind11)

# ---------------------------------------------------------------------------
# Python — must be the same interpreter that will import the extension
# ---------------------------------------------------------------------------
find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)

# ---------------------------------------------------------------------------
# Extension target
# ---------------------------------------------------------------------------
pybind11_add_module(stockindicators src/indicators.cpp)

# ---------------------------------------------------------------------------
# Install: copy .pyd / .so directly into tools/ so Python can import it
# ---------------------------------------------------------------------------
install(
    TARGETS stockindicators
    LIBRARY DESTINATION "${CMAKE_SOURCE_DIR}/.."   # project root — on sys.path when pytest runs
    RUNTIME DESTINATION "${CMAKE_SOURCE_DIR}/.."   # Windows .pyd is a DLL
)
