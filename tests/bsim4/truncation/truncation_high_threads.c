/* Isolated test of the original and experimental transient timestep limits. */
#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"
#include "ngspice/gendefs.h"
#include <omp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if MODEL_VERSION == 45
#include "bsim4v5def.h"
#define FIELD(name) BSIM4v5##name
#elif MODEL_VERSION == 46
#include "bsim4v6def.h"
#define FIELD(name) BSIM4v6##name
#elif MODEL_VERSION == 47
#include "bsim4v7def.h"
#define FIELD(name) BSIM4v7##name
#elif MODEL_VERSION == 48
#include "bsim4def.h"
#define FIELD(name) BSIM4##name
#endif
#define JOIN_(a,b) a##b
#define JOIN(a,b) JOIN_(a,b)
typedef FIELD(instance) Instance;
typedef FIELD(model) Model;
extern int FIELD(trunc)(GENmodel *, CKTcircuit *, double *);
extern int JOIN(baseline_, FIELD(trunc))(GENmodel *, CKTcircuit *, double *);

int main(void)
{
    const int counts[] = {0, 1, 255, 256, 2047, 2048, 4095, 4096, 4097, 8191, 8192, 8193};
    const int threads[] = {1, 8, 16, 32};
    const double initials[] = {1e-15, 1e-9, 1e-6};
    size_t checks = 0, reductions = 0;
    uint64_t checksum = 0;
    omp_set_dynamic(0);
    size_t eligible[4] = {0,0,0,0};
    for (size_t ti=0;ti<4;ti++) {
        int actual_team=0;
        omp_set_num_threads(threads[ti]);
#pragma omp parallel
        {
#pragma omp single
            actual_team=omp_get_num_threads();
        }
        if (actual_team!=threads[ti]) {
            fprintf(stderr,"Requested %d threads, observed %d\n",threads[ti],actual_team);
            return 4;
        }
    }
    for (size_t ci = 0; ci < sizeof(counts)/sizeof(counts[0]); ci++) {
        int count = counts[ci], split = count/2;
        size_t size = ((size_t)count + 1) * 64;
        CKTcircuit ckt;
        Model models[2];
        memset(&ckt, 0, sizeof(ckt));
        memset(models, 0, sizeof(models));
        Instance *instances = calloc(count ? count : 1, sizeof(Instance));
        Instance **array = calloc(count ? count : 1, sizeof(Instance *));
        if (!instances || !array) return 2;
        for (int t = 0; t < 8; t++) {
            ckt.CKTstates[t] = calloc(size, sizeof(double));
            if (!ckt.CKTstates[t]) return 2;
            for (size_t j = 0; j < size; j++)
                ckt.CKTstates[t][j] = (j % 2 ? 1e-6 : 1e-12) *
                    (1 + 0.2*sin((j+1)*(t+1)*0.071));
            if ((size_t)t < sizeof(ckt.CKTdeltaOld)/sizeof(ckt.CKTdeltaOld[0]))
                ckt.CKTdeltaOld[t] = 1e-9 * (1 + t*0.1);
        }
        ckt.CKTabstol = 1e-12;
        ckt.CKTreltol = 1e-4;
        ckt.CKTchgtol = 1e-14;
        ckt.CKTtrtol = 7;
        ckt.CKTdelta = 1e-9;
        models[0].gen.GENnextModel = (GENmodel *)&models[1];
        models[0].gen.GENinstances = split ? (GENinstance *)&instances[0] : NULL;
        models[1].gen.GENinstances = count > split ? (GENinstance *)&instances[split] : NULL;
#ifdef USE_OMP
        models[0].FIELD(InstCount) = count;
        models[0].FIELD(InstanceArray) = array;
#endif
        for (int i = 0; i < count; i++) {
            array[i] = &instances[i];
            instances[i].FIELD(states) = i*64;
            instances[i].gen.GENnextInstance =
                (i+1 == split || i+1 == count) ? NULL : (GENinstance *)&instances[i+1];
        }
        for (int flags = 0; flags < 8; flags++) {
            for (int i = 0; i < count; i++) {
                instances[i].FIELD(trnqsMod) = !!(flags & 1);
                instances[i].FIELD(rbodyMod) = !!(flags & 2);
                instances[i].FIELD(rgateMod) = flags & 4 ? 3 : 0;
            }
            for (int method = 0; method < 8; method++) {
                ckt.CKTintegrateMethod = method < 2 ? TRAPEZOIDAL : GEAR;
                ckt.CKTorder = method < 2 ? method+1 : method-1;
                for (size_t si=0; si<sizeof(initials)/sizeof(initials[0]); si++) {
                    double expected=initials[si];
                    JOIN(baseline_, FIELD(trunc))((GENmodel *)models, &ckt, &expected);
                    for (size_t ti=0; ti<sizeof(threads)/sizeof(threads[0]); ti++) {
                        double actual=initials[si];
                        omp_set_num_threads(threads[ti]);
                        FIELD(trunc)((GENmodel *)models, &ckt, &actual);
                        if (memcmp(&expected,&actual,sizeof(double))) {
                            fprintf(stderr,"Mismatch v%d count=%d flags=%d method=%d order=%d threads=%d: %.17g vs %.17g\n",MODEL_VERSION,count,flags,ckt.CKTintegrateMethod,ckt.CKTorder,threads[ti],actual,expected);
                            return 1;
                        }
                        checks++;
                        if (threads[ti]>1 && count/threads[ti]>=256) eligible[ti]++;
                        reductions += actual < initials[si];
                        uint64_t bits;
                        memcpy(&bits,&actual,sizeof(bits));
                        checksum += bits ^ checks;
                    }
                }
            }
        }
        for (int t=0;t<8;t++) free(ckt.CKTstates[t]);
        free(array);
        free(instances);
    }
    if (!reductions || !eligible[2] || !eligible[3]) return 3;
    printf("eligible_v%d: t8=%zu t16=%zu t32=%zu\n",MODEL_VERSION,eligible[1],eligible[2],eligible[3]);
    printf("{\"model_version\":%d,\"checks\":%zu,\"active_timestep_reductions\":%zu,\"bit_identical\":true,\"checksum\":\"%016llx\"}\n",MODEL_VERSION,checks,reductions,(unsigned long long)checksum);
    return 0;
}
