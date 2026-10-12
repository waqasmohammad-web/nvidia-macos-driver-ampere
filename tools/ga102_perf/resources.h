// Isolated qualification only. Included after the real Vulkan function pointers.
#ifndef GA102_RESOURCES_H
#define GA102_RESOURCES_H
static int ga102_regular_pool(VkDescriptorPool pool);
static uint64_t ga102_sets_allocated, ga102_sets_freed, ga102_sets_live, ga102_sets_peak;
static uint64_t ga102_set_alloc_failures, ga102_set_free_failures;
static uint64_t ga102_dummy_buffer_ns, ga102_dummy_sampled_ns, ga102_dummy_storage_ns;
static uint64_t ga102_dummy_texel_ns, ga102_dummy_sampler_ns;
static _Thread_local int ga102_in_dummy_buffer;
static uint64_t ga102_dummy_heap_allocate_ns, ga102_dummy_heap_map_ns, ga102_dummy_heap_bytes;
static VkResult ga102_allocate_memory(VkDevice device, const VkMemoryAllocateInfo *info,
    const VkAllocationCallbacks *allocator, VkDeviceMemory *memory) {
    uint64_t start=ga102_tick();
    VkResult result=pvkAllocateMemory(device,info,allocator,memory);
    if (ga102_in_dummy_buffer) {
        ga102_dummy_heap_allocate_ns+=ga102_tick()-start;
        if (result==VK_SUCCESS) ga102_dummy_heap_bytes+=info->allocationSize;
    }
    return result;
}
static VkResult ga102_map_memory(VkDevice device, VkDeviceMemory memory, VkDeviceSize offset,
    VkDeviceSize size, VkMemoryMapFlags flags, void **data) {
    uint64_t start=ga102_tick();
    VkResult result=pvkMapMemory(device,memory,offset,size,flags,data);
    if (ga102_in_dummy_buffer) ga102_dummy_heap_map_ns+=ga102_tick()-start;
    return result;
}
// Regular descriptor calls are already serialized by the production descriptor lock.
static VkResult ga102_allocate_sets(VkDevice device, const VkDescriptorSetAllocateInfo *info,
    VkDescriptorSet *sets) {
    VkResult result=pvkAllocateDescriptorSets(device,info,sets);
    if (ga102_regular_pool(info->descriptorPool)) {
        if (result==VK_SUCCESS) {
            ga102_sets_allocated+=info->descriptorSetCount;
            ga102_sets_live+=info->descriptorSetCount;
            if (ga102_sets_live>ga102_sets_peak) ga102_sets_peak=ga102_sets_live;
        } else ga102_set_alloc_failures++;
    }
    return result;
}
static VkResult ga102_free_sets(VkDevice device, VkDescriptorPool pool, uint32_t count,
    const VkDescriptorSet *sets) {
    VkResult result=pvkFreeDescriptorSets(device,pool,count,sets);
    if (ga102_regular_pool(pool)) {
        if (result==VK_SUCCESS) {
            if (count>ga102_sets_live) ga102_stop("descriptor accounting underflow");
            ga102_sets_freed+=count; ga102_sets_live-=count;
        } else ga102_set_free_failures++;
    }
    return result;
}
#endif
