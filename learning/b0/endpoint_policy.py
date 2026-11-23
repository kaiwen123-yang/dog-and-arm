"""Single supervised hinge-conditioned residual used with fixed common door references."""
import numpy as np
import torch

SCHEMA="privileged_hinge_feedback_arm_jaw"
TERMINAL="privileged_hinge_feedback_arm_jaw_terminal"
SCHEMAS=(SCHEMA,TERMINAL)
KNOTS=25
HINGE_SCALE=np.deg2rad(2.8)
DEAD=np.deg2rad(.2)


def reference_clock(path,meta,n,schema):
    kinds=np.asarray(meta["phases"])[np.load(path/"phase.npy")[:n]]
    # The extra end state cannot contribute another command.
    fields=np.zeros((n+1,3),dtype=np.float32)
    if meta["task"]=="push":
        for i,phase in enumerate(("grasp","open")):
            points=np.flatnonzero(kinds==phase)
            if len(points):
                fields[points,i]=1
                fields[points,2]=np.linspace(0,1,len(points))
    if schema==TERMINAL:
        q=np.load(path/"qpos.npy",mmap_mode="r")[:n+1,31]
        hold=np.flatnonzero(kinds=="hold")
        if len(hold):
            remaining=float(np.median(q[hold]))-q
        else:
            remaining=np.zeros(n+1)
        fields=np.column_stack((fields,remaining))
    return fields


def features(goal):
    # Current observed or predicted hinge minus the same fixed reference frame.
    error,grasp,opening,progress=goal[:,540:544].unbind(dim=1)
    gate=((error-DEAD)/DEAD).clamp(0.,1.)
    commanded_error=error
    if goal.shape[-1]==545:
        # As the reference enters the final 3.3 degrees, blend live-angle
        # feedback toward the frozen reference grasp-hold equilibrium. The
        # identical nominal deadband and real-angle gate stay in effect.
        remaining=goal[:,544]
        blend=opening*((np.deg2rad(3.3)-remaining)/np.deg2rad(1.)).clamp(0.,1.)
        commanded_error=torch.lerp(error,remaining,blend)
    arm_scale=gate*(commanded_error/HINGE_SCALE).clamp(0.,2.)
    jaw_scale=gate*(error/np.deg2rad(1.)).clamp(0.,1.)
    slots=torch.arange(KNOTS,device=goal.device,dtype=goal.dtype)
    hats=(1.-(progress[:,None]*(KNOTS-1)-slots).abs()).clamp_min(0.)
    phi=torch.cat((grasp[:,None]*hats,opening[:,None]*hats),dim=1)
    return phi*arm_scale[:,None],phi*jaw_scale[:,None]
