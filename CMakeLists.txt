cmake_minimum_required(VERSION 3.20)
project(Kinect2Linux LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${PROJECT_SOURCE_DIR}/bin")

option(KINECT2_ENABLE_HARDWARE "Build opt-in broker with local libfreenect2" OFF)
set(LIBFREENECT2_DIR "${PROJECT_SOURCE_DIR}/../libfreenect2-omp" CACHE PATH
    "Existing local patched libfreenect2-omp checkout")

add_compile_options(-Wall -Wextra -Wpedantic -Werror)
find_package(Threads REQUIRED)

# Separate compiled targets: Ninja rebuilds only affected dependencies.
add_library(kinect2_discovery STATIC core/sensor_backend.cpp)
add_library(kinect2_session STATIC core/device_session.cpp)
add_library(kinect2_hardware_stub STATIC core/libfreenect2_hardware.cpp)
add_library(kinect2_worker_supervisor STATIC core/worker_process.cpp)
add_library(kinect2_frame_hub STATIC core/frame_hub.cpp)
foreach(target kinect2_discovery kinect2_session kinect2_hardware_stub
               kinect2_worker_supervisor kinect2_frame_hub)
  target_include_directories(${target} PUBLIC "${PROJECT_SOURCE_DIR}")
endforeach()

add_executable(kinect2-worker workers/kinect2_worker.cpp)
target_link_libraries(kinect2-worker PRIVATE Threads::Threads)

add_executable(kinect2-broker src/kinect_broker.cpp)
target_link_libraries(kinect2-broker PRIVATE kinect2_discovery kinect2_session
  kinect2_hardware_stub kinect2_worker_supervisor kinect2_frame_hub Threads::Threads)

if(KINECT2_ENABLE_HARDWARE)
  set(KINECT2_SO_DIR "${LIBFREENECT2_DIR}/build-omp/lib")
  if(NOT EXISTS "${LIBFREENECT2_DIR}/include/libfreenect2/libfreenect2.hpp"
     OR NOT EXISTS "${KINECT2_SO_DIR}/libfreenect2.so")
    message(FATAL_ERROR "Missing patched libfreenect2: ${LIBFREENECT2_DIR}")
  endif()
  add_library(kinect2_hardware_native STATIC core/libfreenect2_hardware.cpp)
  target_include_directories(kinect2_hardware_native PRIVATE
    "${PROJECT_SOURCE_DIR}" "${LIBFREENECT2_DIR}/include"
    "${LIBFREENECT2_DIR}/build-omp")
  target_compile_definitions(kinect2_hardware_native PRIVATE KINECT2_WITH_LIBFREENECT2)
  add_library(kinect2_local_freenect2 SHARED IMPORTED)
  set_target_properties(kinect2_local_freenect2 PROPERTIES
    IMPORTED_LOCATION "${KINECT2_SO_DIR}/libfreenect2.so")
  add_executable(kinect2-broker-hw src/kinect_broker.cpp)
  target_link_libraries(kinect2-broker-hw PRIVATE kinect2_discovery
    kinect2_session kinect2_hardware_native kinect2_worker_supervisor
    kinect2_frame_hub kinect2_local_freenect2 Threads::Threads)
  set_target_properties(kinect2-broker-hw PROPERTIES
    BUILD_RPATH "${KINECT2_SO_DIR}")
endif()

enable_testing()
add_executable(test_sensor_backend tests/native/test_sensor_backend.cpp)
target_link_libraries(test_sensor_backend PRIVATE kinect2_discovery)
add_test(NAME sensor_backend COMMAND test_sensor_backend)

add_executable(test_device_session tests/native/test_device_session.cpp)
target_link_libraries(test_device_session PRIVATE kinect2_session)
add_test(NAME device_session COMMAND test_device_session)

add_executable(test_sequence_gap_tracker tests/native/test_sequence_gap_tracker.cpp)
target_include_directories(test_sequence_gap_tracker PRIVATE "${PROJECT_SOURCE_DIR}")
add_test(NAME sequence_gap_tracker COMMAND test_sequence_gap_tracker)

add_executable(test_worker_process tests/native/test_worker_process.cpp)
target_link_libraries(test_worker_process PRIVATE kinect2_worker_supervisor)
add_test(NAME worker_process COMMAND test_worker_process "$<TARGET_FILE:kinect2-worker>")

# Existing native tests use assert() with meaningful side effects. CMake
# Release defines NDEBUG, so explicitly keep assertions enabled in test code.
foreach(test_target test_sensor_backend test_device_session test_sequence_gap_tracker test_worker_process)
  target_compile_options(${test_target} PRIVATE -UNDEBUG)
endforeach()
