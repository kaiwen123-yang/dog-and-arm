"""Isolate TorchScript's forward-AD behavior with an analytic identity rotation; no model calls."""
import argparse
import json
from pathlib import Path

import torch
from mjlab.utils.lab_api.math import quat_apply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    fp64 = dict(device='cuda', dtype=torch.float64)
    q = torch.tensor([[1., 0., 0., 0.]], **fp64)
    v = torch.tensor([[2., 3., 4.]], **fp64)
    d = torch.tensor([[.1, .2, .3]], **fp64)
    details = dict(torch_version=torch.__version__, q=q.tolist(), v=v.tolist(), d=d.tolist())
    with torch.no_grad():
        for _ in range(3):
            quat_apply(q, v)
    for name, optimize in [('native_dual', True), ('optimization_disabled', False)]:
        with torch.jit.optimized_execution(optimize), torch.no_grad(), torch.autograd.forward_ad.dual_level():
            dual = torch.autograd.forward_ad.make_dual(v, d)
            pair = torch.autograd.forward_ad.unpack_dual(quat_apply(q, dual))
            details[name] = dict(primal=pair.primal.tolist(), tangent=None if pair.tangent is None else pair.tangent.tolist())
    x = v.clone().requires_grad_(True)
    details['reverse_vjp'] = torch.autograd.grad((quat_apply(q, x)*d).sum(), x)[0].tolist()
    _, derivative = torch.autograd.functional.jvp(lambda a: quat_apply(q, a), v, d)
    details['corrected_jvp'] = derivative.tolist()
    assert details['corrected_jvp'] == details['reverse_vjp'] == d.tolist()
    args.output.write_text(json.dumps(details, indent=2)+'\n')


if __name__ == '__main__':
    main()
