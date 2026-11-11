// Standalone, CPU-readable Vulkan 1.0 Compute runner for the mask experiment.
// No Kinect access, no Microsoft code, and no production broker integration.
#include <vulkan/vulkan.h>

#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
constexpr std::size_t kInputBytes = 512u * 424u * 2u;
constexpr std::uint32_t kTiles = 64u * 53u;
constexpr VkDeviceSize kOutputBytes = VkDeviceSize(kTiles) * 4u;

void check(VkResult status, const char* operation) {
    if (status != VK_SUCCESS) {
        throw std::runtime_error(std::string(operation) +
                                 " failed with VkResult " + std::to_string(status));
    }
}

std::vector<std::uint8_t> read_file(const std::string& filename) {
    std::ifstream file(filename, std::ios::binary | std::ios::ate);
    if (!file) {
        throw std::runtime_error("cannot open input file: " + filename);
    }
    const auto end = file.tellg();
    if (end < 0) {
        throw std::runtime_error("cannot determine file length: " + filename);
    }
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(end));
    file.seekg(0, std::ios::beg);
    if (!bytes.empty() &&
        !file.read(reinterpret_cast<char*>(bytes.data()), bytes.size())) {
        throw std::runtime_error("cannot read file: " + filename);
    }
    return bytes;
}

struct Buffer {
    VkBuffer handle = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    bool coherent = false;
};

struct Vulkan {
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    std::uint32_t family = 0;
    VkDescriptorSetLayout set_layout = VK_NULL_HANDLE;
    VkDescriptorPool descriptor_pool = VK_NULL_HANDLE;
    VkPipelineLayout pipeline_layout = VK_NULL_HANDLE;
    VkShaderModule shader_module = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkCommandPool command_pool = VK_NULL_HANDLE;
    Buffer input;
    Buffer output;

    Vulkan() = default;
    Vulkan(const Vulkan&) = delete;
    Vulkan& operator=(const Vulkan&) = delete;

    ~Vulkan() {
        if (device) {
            vkDeviceWaitIdle(device);
            if (command_pool) vkDestroyCommandPool(device, command_pool, nullptr);
            if (pipeline) vkDestroyPipeline(device, pipeline, nullptr);
            if (shader_module) vkDestroyShaderModule(device, shader_module, nullptr);
            if (pipeline_layout) vkDestroyPipelineLayout(device, pipeline_layout, nullptr);
            if (descriptor_pool) vkDestroyDescriptorPool(device, descriptor_pool, nullptr);
            if (set_layout) vkDestroyDescriptorSetLayout(device, set_layout, nullptr);
            if (output.handle) vkDestroyBuffer(device, output.handle, nullptr);
            if (output.memory) vkFreeMemory(device, output.memory, nullptr);
            if (input.handle) vkDestroyBuffer(device, input.handle, nullptr);
            if (input.memory) vkFreeMemory(device, input.memory, nullptr);
            vkDestroyDevice(device, nullptr);
        }
        if (instance) vkDestroyInstance(instance, nullptr);
    }

    void initialize() {
        VkApplicationInfo app{};
        app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app.pApplicationName = "Kinect2Linux Vulkan mask research";
        app.apiVersion = VK_API_VERSION_1_0;

        VkInstanceCreateInfo create{};
        create.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        create.pApplicationInfo = &app;
        check(vkCreateInstance(&create, nullptr, &instance), "vkCreateInstance");

        std::uint32_t n_devices = 0;
        check(vkEnumeratePhysicalDevices(instance, &n_devices, nullptr),
              "vkEnumeratePhysicalDevices(count)");
        if (!n_devices) throw std::runtime_error("no Vulkan physical device found");
        std::vector<VkPhysicalDevice> devices(n_devices);
        check(vkEnumeratePhysicalDevices(instance, &n_devices, devices.data()),
              "vkEnumeratePhysicalDevices(list)");

        bool found = false;
        for (VkPhysicalDevice candidate : devices) {
            std::uint32_t n_families = 0;
            vkGetPhysicalDeviceQueueFamilyProperties(candidate, &n_families, nullptr);
            std::vector<VkQueueFamilyProperties> families(n_families);
            vkGetPhysicalDeviceQueueFamilyProperties(candidate, &n_families,
                                                    families.data());
            for (std::uint32_t i = 0; i < n_families; ++i) {
                if ((families[i].queueFlags & VK_QUEUE_COMPUTE_BIT) &&
                    families[i].queueCount > 0) {
                    physical = candidate;
                    family = i;
                    found = true;
                    break;
                }
            }
            if (found) break;
        }
        if (!found) throw std::runtime_error("no Vulkan compute queue available");

        const float priority = 1.0f;
        VkDeviceQueueCreateInfo queue_info{};
        queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_info.queueFamilyIndex = family;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        VkDeviceCreateInfo device_info{};
        device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        check(vkCreateDevice(physical, &device_info, nullptr, &device),
              "vkCreateDevice");
        vkGetDeviceQueue(device, family, 0, &queue);
    }

    void create_buffer(VkDeviceSize size, Buffer& buffer) {
        VkBufferCreateInfo info{};
        info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        info.size = size;
        info.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        check(vkCreateBuffer(device, &info, nullptr, &buffer.handle),
              "vkCreateBuffer");

        VkMemoryRequirements requirements{};
        vkGetBufferMemoryRequirements(device, buffer.handle, &requirements);
        VkPhysicalDeviceMemoryProperties memory_properties{};
        vkGetPhysicalDeviceMemoryProperties(physical, &memory_properties);

        std::uint32_t chosen = memory_properties.memoryTypeCount;
        // Prefer coherent memory, but support noncoherent memory as well.
        for (int coherent = 1; coherent >= 0; --coherent) {
            for (std::uint32_t i = 0; i < memory_properties.memoryTypeCount; ++i) {
                const auto flags = memory_properties.memoryTypes[i].propertyFlags;
                if (!(requirements.memoryTypeBits & (1u << i))) continue;
                if (!(flags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)) continue;
                if (coherent && !(flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) continue;
                chosen = i;
                buffer.coherent = (flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) != 0;
                break;
            }
            if (chosen < memory_properties.memoryTypeCount) break;
        }
        if (chosen == memory_properties.memoryTypeCount) {
            throw std::runtime_error("no host-visible memory type for storage buffer");
        }

        VkMemoryAllocateInfo allocate{};
        allocate.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocate.allocationSize = requirements.size;
        allocate.memoryTypeIndex = chosen;
        check(vkAllocateMemory(device, &allocate, nullptr, &buffer.memory),
              "vkAllocateMemory");
        check(vkBindBufferMemory(device, buffer.handle, buffer.memory, 0),
              "vkBindBufferMemory");
    }

    void upload(const Buffer& buffer, const void* data, std::size_t size) {
        void* mapped = nullptr;
        check(vkMapMemory(device, buffer.memory, 0, VK_WHOLE_SIZE, 0, &mapped),
              "vkMapMemory(input)");
        std::memcpy(mapped, data, size);
        if (!buffer.coherent) {
            VkMappedMemoryRange range{};
            range.sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE;
            range.memory = buffer.memory;
            range.offset = 0;
            range.size = VK_WHOLE_SIZE;
            check(vkFlushMappedMemoryRanges(device, 1, &range),
                  "vkFlushMappedMemoryRanges");
        }
        vkUnmapMemory(device, buffer.memory);
    }

    std::vector<std::uint32_t> download(const Buffer& buffer) {
        void* mapped = nullptr;
        check(vkMapMemory(device, buffer.memory, 0, VK_WHOLE_SIZE, 0, &mapped),
              "vkMapMemory(output)");
        if (!buffer.coherent) {
            VkMappedMemoryRange range{};
            range.sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE;
            range.memory = buffer.memory;
            range.offset = 0;
            range.size = VK_WHOLE_SIZE;
            check(vkInvalidateMappedMemoryRanges(device, 1, &range),
                  "vkInvalidateMappedMemoryRanges");
        }
        std::vector<std::uint32_t> words(kTiles);
        std::memcpy(words.data(), mapped, static_cast<std::size_t>(kOutputBytes));
        vkUnmapMemory(device, buffer.memory);
        return words;
    }

    void run(const std::vector<std::uint8_t>& source,
             const std::vector<std::uint8_t>& spirv) {
        create_buffer(kInputBytes, input);
        create_buffer(kOutputBytes, output);
        upload(input, source.data(), source.size());

        const VkDescriptorSetLayoutBinding bindings[] = {
            {0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
            {1, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
        };
        VkDescriptorSetLayoutCreateInfo layout_info{};
        layout_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        layout_info.bindingCount = 2;
        layout_info.pBindings = bindings;
        check(vkCreateDescriptorSetLayout(device, &layout_info, nullptr, &set_layout),
              "vkCreateDescriptorSetLayout");

        VkPipelineLayoutCreateInfo pipeline_layout_info{};
        pipeline_layout_info.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        pipeline_layout_info.setLayoutCount = 1;
        pipeline_layout_info.pSetLayouts = &set_layout;
        check(vkCreatePipelineLayout(device, &pipeline_layout_info, nullptr,
                                     &pipeline_layout), "vkCreatePipelineLayout");

        VkDescriptorPoolSize pool_size{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 2};
        VkDescriptorPoolCreateInfo pool_info{};
        pool_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
        pool_info.maxSets = 1;
        pool_info.poolSizeCount = 1;
        pool_info.pPoolSizes = &pool_size;
        check(vkCreateDescriptorPool(device, &pool_info, nullptr, &descriptor_pool),
              "vkCreateDescriptorPool");

        VkDescriptorSetAllocateInfo descriptor_alloc{};
        descriptor_alloc.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        descriptor_alloc.descriptorPool = descriptor_pool;
        descriptor_alloc.descriptorSetCount = 1;
        descriptor_alloc.pSetLayouts = &set_layout;
        VkDescriptorSet descriptor_set = VK_NULL_HANDLE;
        check(vkAllocateDescriptorSets(device, &descriptor_alloc, &descriptor_set),
              "vkAllocateDescriptorSets");

        const VkDescriptorBufferInfo buffer_infos[] = {
            {input.handle, 0, kInputBytes},
            {output.handle, 0, kOutputBytes},
        };
        VkWriteDescriptorSet writes[2]{};
        for (std::uint32_t i = 0; i < 2; ++i) {
            writes[i].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
            writes[i].dstSet = descriptor_set;
            writes[i].dstBinding = i;
            writes[i].descriptorCount = 1;
            writes[i].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
            writes[i].pBufferInfo = &buffer_infos[i];
        }
        vkUpdateDescriptorSets(device, 2, writes, 0, nullptr);

        std::vector<std::uint32_t> code(spirv.size() / 4u);
        std::memcpy(code.data(), spirv.data(), spirv.size());
        VkShaderModuleCreateInfo shader_info{};
        shader_info.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        shader_info.codeSize = spirv.size();
        shader_info.pCode = code.data();
        check(vkCreateShaderModule(device, &shader_info, nullptr, &shader_module),
              "vkCreateShaderModule");

        VkPipelineShaderStageCreateInfo stage{};
        stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        stage.module = shader_module;
        stage.pName = "main";
        VkComputePipelineCreateInfo compute{};
        compute.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
        compute.stage = stage;
        compute.layout = pipeline_layout;
        check(vkCreateComputePipelines(device, VK_NULL_HANDLE, 1, &compute, nullptr,
                                       &pipeline), "vkCreateComputePipelines");

        VkCommandPoolCreateInfo command_pool_info{};
        command_pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        command_pool_info.queueFamilyIndex = family;
        check(vkCreateCommandPool(device, &command_pool_info, nullptr, &command_pool),
              "vkCreateCommandPool");

        VkCommandBufferAllocateInfo command_alloc{};
        command_alloc.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        command_alloc.commandPool = command_pool;
        command_alloc.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        command_alloc.commandBufferCount = 1;
        VkCommandBuffer cmd = VK_NULL_HANDLE;
        check(vkAllocateCommandBuffers(device, &command_alloc, &cmd),
              "vkAllocateCommandBuffers");

        VkCommandBufferBeginInfo begin{};
        begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(cmd, &begin), "vkBeginCommandBuffer");
        vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
        vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline_layout,
                                0, 1, &descriptor_set, 0, nullptr);
        vkCmdDispatch(cmd, 53, 1, 1);  // 53 * 64 = 3392 invocations.

        VkBufferMemoryBarrier barrier{};
        barrier.sType = VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER;
        barrier.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
        barrier.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
        barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.buffer = output.handle;
        barrier.offset = 0;
        barrier.size = kOutputBytes;
        vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                             VK_PIPELINE_STAGE_HOST_BIT, 0, 0, nullptr,
                             1, &barrier, 0, nullptr);
        check(vkEndCommandBuffer(cmd), "vkEndCommandBuffer");

        VkSubmitInfo submit{};
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &cmd;
        check(vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE), "vkQueueSubmit");
        check(vkQueueWaitIdle(queue), "vkQueueWaitIdle");
    }
};

void execute(const std::string& shader_file, const std::string& input_file,
             const std::string& output_file) {
    const auto source = read_file(input_file);
    if (source.size() != kInputBytes) {
        throw std::runtime_error("input must be exactly 512*424*2 bytes (packed R16_UINT)");
    }

    const auto spirv = read_file(shader_file);
    if (spirv.size() < 20 || spirv.size() % 4 != 0 ||
        spirv[0] != 0x03 || spirv[1] != 0x02 || spirv[2] != 0x23 ||
        spirv[3] != 0x07) {
        throw std::runtime_error("shader is not a valid SPIR-V byte stream");
    }

    Vulkan vk;
    vk.initialize();
    vk.run(source, spirv);
    auto masks = vk.download(vk.output);

    std::vector<std::uint8_t> byte_masks(kTiles);
    for (std::size_t i = 0; i < masks.size(); ++i) {
        if (masks[i] > 7) {
            throw std::runtime_error("GPU output contains values outside 3-bit mask");
        }
        byte_masks[i] = static_cast<std::uint8_t>(masks[i]);
    }

    std::ofstream out(output_file, std::ios::binary | std::ios::trunc);
    if (!out || !out.write(reinterpret_cast<const char*>(byte_masks.data()),
                           byte_masks.size())) {
        throw std::runtime_error("cannot write output file: " + output_file);
    }
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "Usage: " << argv[0]
                  << " <shader.spv> <packed-512x424.r16> <output-3392-byte-mask>\n";
        return 2;
    }
    try {
        execute(argv[1], argv[2], argv[3]);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Vulkan mask runner: " << error.what() << '\n';
        return 1;
    }
}
