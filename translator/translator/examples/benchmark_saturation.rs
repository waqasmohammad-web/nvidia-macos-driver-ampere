//! Bounded, owned color-filter compilation workload. Times the native pipeline
//! without validator subprocesses; validates the emitted shader separately.
//! Run the same executable arguments for baseline and candidate builds.
use metal2vulkan::{
    passes::{Stage, TransformOptions},
    reflect::KernelDispatch,
};
use std::{hint::black_box, path::PathBuf, time::Instant};

fn source(cells: usize, lanes: usize, fast: bool) -> String {
    let ty = if lanes == 1 {
        "float".to_owned()
    } else {
        format!("<{lanes} x float>")
    };
    let name = format!(
        "air.{}saturate.{}f32",
        if fast { "fast_" } else { "" },
        if lanes == 1 {
            "".to_owned()
        } else {
            format!("v{lanes}")
        }
    );
    let constant = |value: f64| {
        if lanes == 1 {
            format!("{value:.6e}")
        } else {
            format!("<{}>", vec![format!("float {value:.6e}"); lanes].join(", "))
        }
    };
    let mut ll = format!("define void @k(ptr addrspace(1) %input, ptr addrspace(1) %output) {{\nentry:\n  %seed = load {ty}, ptr addrspace(1) %input, align 4\n");
    for i in 0..cells {
        ll.push_str(&format!("  %scaled{i} = fmul {ty} %seed, {}\n  %sat{i} = call {ty} @{name}({ty} %scaled{i})\n  %dst{i} = getelementptr {ty}, ptr addrspace(1) %output, i64 {i}\n  store {ty} %sat{i}, ptr addrspace(1) %dst{i}, align 4\n", constant(0.5 + i as f64 / 1024.0)));
    }
    ll.push_str(&format!("  ret void\n}}\ndeclare {ty} @{name}({ty})\n"));
    ll.push_str(r#"
!air.kernel = !{!0}
!0 = !{ptr @k, !1, !2}
!1 = !{}
!2 = !{!3, !4}
!3 = !{i32 0, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_name", !"float", !"air.arg_name", !"input"}
!4 = !{i32 1, !"air.buffer", !"air.location_index", i32 1, i32 1, !"air.write", !"air.address_space", i32 1, !"air.arg_type_name", !"float", !"air.arg_name", !"output"}
"#);
    ll
}
fn main() {
    let mut args = std::env::args().skip(1);
    let output = PathBuf::from(
        args.next()
            .expect("usage: benchmark_saturation OUTPUT_DIR [SAMPLES]"),
    );
    let samples: usize = args
        .next()
        .unwrap_or_else(|| "9".into())
        .parse()
        .expect("samples");
    assert!((1..=100).contains(&samples));
    std::fs::create_dir_all(&output).expect("output directory");
    for (cells, lanes, fast) in [
        (16, 4, false),
        (64, 4, false),
        (256, 4, false),
        (64, 1, false),
        (64, 4, true),
    ] {
        let label = format!(
            "saturation-{cells}-{lanes}-{}",
            if fast { "fast" } else { "precise" }
        );
        let ll = source(cells, lanes, fast);
        let options = TransformOptions {
            kernel_dispatch: Some(KernelDispatch::Workgroups),
            ..Default::default()
        };
        let translate = || {
            metal2vulkan::translate_native_no_retry_with_options(
                black_box(&ll),
                Stage::Kernel,
                options,
            )
            .expect("translate")
        };
        let warm = translate();
        metal2vulkan::tools::spirv_val_bytes(&warm, &output).expect("real validation of warmup");
        let mut times = Vec::new();
        let mut last = warm;
        for _ in 0..samples {
            let start = Instant::now();
            last = translate();
            times.push(start.elapsed().as_nanos() as u64);
            black_box(&last);
        }
        metal2vulkan::tools::spirv_val_bytes(&last, &output)
            .expect("real validation of measured output");
        std::fs::write(output.join(format!("{label}.spv")), &last).expect("write shader");
        std::fs::write(output.join(format!("{label}.ll")), ll).expect("write owned workload");
        println!(
            "{}",
            serde_json::json!({"workload":label,"samples_ns":times,"bytes":last.len(),"profile":if cfg!(debug_assertions) { "debug_assertions" } else { "no_debug_assertions" },"validator_in_timing":false})
        );
    }
}
