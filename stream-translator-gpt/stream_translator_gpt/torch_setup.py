def disable_nnpack(torch_module=None) -> None:
    try:
        if torch_module is None:
            import torch as torch_module
        torch_module.backends.nnpack.set_flags(False)
    except Exception:
        pass
