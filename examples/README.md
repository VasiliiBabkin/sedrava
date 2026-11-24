# Sedrava examples

Run commands with the current Rust CLI sedrava. Every example has its own supported target; do not assume all generators support all constructs.

| Example | Try |
| --- | --- |
| counter.sdr | sedrava test examples/counter.sdr |
| reference_09.sdr | sedrava run examples/reference_09.sdr add add |
| task_manager.sdr | sedrava check examples/task_manager.sdr |
| task_manager_navigation.sdr | sedrava check examples/task_manager_navigation.sdr |
| service_journal.sdr | sedrava build webapp examples/service_journal.sdr --output build/journal |
| platform_site.sdr | sedrava build site examples/platform_site.sdr --output build/site |
| sales_demo/sales_api.sdr | sedrava database-api check examples/sales_demo/sales_api.sdr |
| self_host/function_compiler_a511b.sdr | sedrava check examples/self_host/function_compiler_a511b.sdr |

[Guide](../docs/README.ru.md) · [Sales demo](../docs/SALES_DEMO_A21.ru.md) · [Self-host compiler](../docs/SELF_HOSTING_FUNCTION_COMPILER_A511B.ru.md).
