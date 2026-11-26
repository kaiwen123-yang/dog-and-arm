/* Read solved wheel/ground forces using MuJoCo 3.3's own cone conversion.
 * Any active pair outside this narrow case is delegated to the original meter.
 */
#include <mujoco/mujoco.h>
#include <stddef.h>

int mm03_native_abi(void) {
    return mj_version() == mjVERSION_HEADER && sizeof(mjtNum) == sizeof(double)
           ? mj_version() : 0;
}

int mm03_wheel_normals(const mjModel* model, const mjData* data, int floor_geom,
                       const int* geom_to_wheel, int ngeom, double result[4]) {
    if (model == NULL || data == NULL || ngeom != model->ngeom) return 0;
    for (int w = 0; w < 4; ++w) result[w] = 0.0;
    for (int i = 0; i < data->ncon; ++i) {
        const mjContact* c = data->contact + i;
        if (c->efc_address < 0) continue;
        int geom;
        if (c->geom[0] == floor_geom) geom = c->geom[1];
        else if (c->geom[1] == floor_geom) geom = c->geom[0];
        else return 0;
        if (geom < 0 || geom >= ngeom) return 0;
        int w = geom_to_wheel[geom];
        if (w < 0 || w >= 4) return 0;
        mjtNum force[6];
        mj_contactForce(model, data, i, force);
        if (!(force[0] <= 0.0)) result[w] += force[0];
    }
    return 1;
}
