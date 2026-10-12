// Owned offscreen graphics workload. Runtime-bound sampler index is deliberate.
#include <metal_stdlib>
using namespace metal;
vertex float4 ga102_runtime_vertex(uint index [[vertex_id]]) {
    return float4(index == 0 ? float2(-1,-1) : (index == 1 ? float2(3,-1) : float2(-1,3)),0,1);
}
fragment float4 ga102_runtime_fragment(texture2d<float> image [[texture(0)]], sampler bound [[sampler(3)]]) {
    return image.sample(bound, float2(2.25,3.75));
}
