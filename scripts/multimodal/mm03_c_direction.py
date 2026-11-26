"""Native signed finite differences at fixed legal snapshots, stratified by contact at the anchor."""
import torch


def directional(actor, objective, native, cap):
    contact=objective.targets["prev_contact"][:,0,:2].any(-1)
    perturbations=[]
    total_model=total_physics=0
    bias=actor.head[-1].bias
    original=bias.detach().clone()
    precision=torch.get_float32_matmul_precision()
    try:
        torch.set_float32_matmul_precision("highest")
        for name,mask in (("no_contact",~contact),("finger_contact",contact)):
            rows=torch.where(mask)[0][:4]
            if not len(rows):
                perturbations.append(dict(stratum=name,n=0))
                continue
            base,info=objective.loss_for(actor,rows,"C32",cap)
            grad,=torch.autograd.grad(base,bias)
            total_model+=info["model_queries"]
            norm=grad.norm()
            if not torch.isfinite(norm):
                raise FloatingPointError("Nonfinite parent direction")
            direction=grad.detach()/norm.clamp_min(1e-16)
            outputs={}
            observed={}
            for eps in (.008,.002):
                values={}
                for sign in (1,-1):
                    with torch.no_grad():
                        bias.copy_(original+(sign*eps)*direction)
                        imag,si=objective.loss_for(actor,rows,"C32",cap)
                        actual,sa=objective.loss_for(actor,rows,"CF32",cap,native)
                    total_model+=si["model_queries"]+sa["model_queries"]
                    total_physics+=sa["native_substeps"]
                    values[sign]=[float(imag),float(actual)]
                    observed[f"{eps}_{sign}"]=dict(native_substeps=sa["native_substeps"],
                                                  legal=int(sa["valid"].sum()),terminal=len(sa["terminals"]))
                outputs[str(eps)]=dict(imagination_difference=(values[1][0]-values[-1][0])/(2*eps),
                                       native_difference=(values[1][1]-values[-1][1])/(2*eps),
                                       plus=values[1],minus=values[-1])
            with torch.no_grad():
                bias.copy_(original)
            perturbations.append(dict(stratum=name,n=len(rows),anchors=[objective.keys[i] for i in rows.tolist()],
                                      model_autograd=float(norm),response=outputs,measured=observed))
    finally:
        with torch.no_grad():
            bias.copy_(original)
        torch.set_float32_matmul_precision(precision)
    return dict(parameter="final actor bias, unit gradient direction",strata=perturbations,
                model_queries=total_model,native_substeps=total_physics,actor_updates=0)
