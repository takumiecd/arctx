# Optimization Agent (optagent)

A generalized optimization agent framework that can optimize:
- **Sparse kernels** (CUDA/OpenCL)
- **Configuration parameters**
- **Database queries**
- **Any measurable system**

## Philosophy

Instead of hardcoding optimization logic for a specific domain, `optagent` provides:

1. **Pluggable Strategies** - Swap optimization targets without changing the core
2. **Backend Abstraction** - Use OpenCode, Claude, Codex, or your own LLM
3. **Evaluation Framework** - Fair multi-size benchmarking with statistical rigor
4. **Workflow Engine** - Deterministic state machine for reproducible optimization

## Quick Start

```python
from optagent import ManagerAgent, BatchOptimizer
from optagent.strategies.kernel import KernelOptimizationStrategy
from optagent.backends import OpenCodeBackend
from optagent.evaluation import MultiSizeEvaluator

# Configure strategy
strategy = KernelOptimizationStrategy(
    formats=["CSC", "CSCR", "BSC"],
    operations=["linear_forward", "conv2d_forward"],
)

# Configure backend
backend = OpenCodeBackend(model="opencode-go/kimi-k2.6")

# Configure evaluator
evaluator = MultiSizeEvaluator(scales=["small", "medium", "large"])

# Create optimizer
optimizer = ManagerAgent(
    strategy=strategy,
    backend=backend,
    evaluator=evaluator,
)

# Run optimization
result = optimizer.optimize(requirement)
```

## Architecture

```
optagent/
├── core/           # Workflow engine & state management
├── backends/       # LLM provider integrations
├── evaluation/     # Benchmarking & measurement
├── strategies/     # Domain-specific optimization logic
├── artifacts/      # Code generation & validation
└── reporting/      # Results aggregation & visualization
```

## Installation

```bash
pip install -e ".[dev,kernel]"
```

## Testing

```bash
pytest tests/ -v
```

## License

MIT
