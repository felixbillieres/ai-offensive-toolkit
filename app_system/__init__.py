"""AI application and system-level attacks — MCP, SSRF, model tampering, stealing, DoS."""

from .mcp_attack import test_ssrf, test_tool_abuse, test_rogue_actions
from .model_tampering import (
    inject_weight_backdoor, modify_output_bias,
    compute_model_hash, compute_weight_fingerprint,
    verify_model_integrity, diff_models,
)
from .model_stealing import steal_model, collect_samples, train_surrogate
from .sponge_attack import (
    analyze_tokenization, find_inefficient_inputs,
    genetic_sponge, benchmark_target,
)
