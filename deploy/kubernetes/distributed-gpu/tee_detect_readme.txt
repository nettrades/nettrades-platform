 system can automatically detect every major TEE/Confidential Computing technology. The detection is non-privileged (root not required for queries, only for enabling the features), and can be integrated directly into the NETTRADES agent with the Python module provided below.
Detection Methods for Each Technology
NVIDIA Confidential Computing (H100/H200)

The nvidia-smi tool provides a dedicated sub-command:
bash

sudo nvidia-smi conf-compute -f
# Output: "CC status: ON" (if enabled) or "CC status: OFF"

NVIDIA Confidential Computing is "a built-in security feature of Hopper that makes NVIDIA H100 the world's first accelerator with confidential computing capabilities". The NVIDIA GPU Admin Tools provide programmatic controls for confidential computing on H100 and other supported GPUs. The Secure AI Compatibility Matrix lists all supported combinations of GPU models, VBIOS versions, CUDA driver versions, and Confidential Computing modes.

The raw device-file interface is also available at /dev/nvidia-cc when CC mode is active, providing a simple filesystem check before invoking nvidia-smi.
Intel SGX

Detection requires checking CPUID leaf 12h. Intel's documentation states explicitly: "Ensure your Intel Xeon processor supports SGX by checking the CPUID leaf 12h. If SGX is not enabled in BIOS, the BIOS will not load MCHECK, and hence there will be no CPUID leaf 12h to report SGX status".

The most practical user-space approach uses the cpuid tool:
bash

cpuid -l 0x12 | grep -i sgx
# If SGX is available, output includes: SGX_LC: SGX launch config supported = true

Alternatively, the Linux kernel exposes SGX status via /sys/devices/system/cpu/sgx/status (kernel ≥5.11), which provides a filesystem check without external tools. For applications that need the detection integrated in-process, the libcpuid C library provides struct cpu_sgx_t with INTEL_SGX1 and INTEL_SGX2 feature flags.

Intel has deprecated SGX on all consumer platforms (12th-gen Core and later). SGX is now available only on Xeon server processors with SGX explicitly enabled in BIOS.
AMD SEV-SNP

AMD provides an official Python script that queries MSRs and CPUID functions:
bash

python ./sev_component_test.py
# Checks CPUID function 0x8000001f bit 1 for SEV
# Checks MSR 0xC0010010 bit 23 for SME
# Checks individual SNP support

This script is "used to query a host system's capabilities to use AMD's encryption technologies: SEV, SEV-ES and SEV-SNP". For production code, the same information can be obtained by reading CPUID and MSRs directly, or by using the kernel's cc_platform_*() interface. The Linux kernel commit f742b90e added CC_ATTR_GUEST_SEV_SNP which "can be used by the guest to query whether the SNP feature is active".
Intel TDX

Intel TDX shares the same CPUID-based detection pattern as SGX but uses a different leaf. The most reliable method at user level is the virt-what-cvm tool, which is specifically designed to "detect if the program is running in a confidential virtual machine" and can identify Intel TDX guests. TDX detection is primarily relevant inside a guest VM; on bare-metal hosts, the kernel exposes TDX capability via /sys/devices/system/cpu/microcode/tdx and related kernel parameters.