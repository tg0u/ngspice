/**** BSIM4.5.0 Released by Xuemei (Jane) Xi 07/29/2005 ****/

/**********
 * Copyright 2004 Regents of the University of California. All rights reserved.
 * File: b4trunc.c of BSIM4.5.0.
 * Author: 2000 Weidong Liu
 * Authors: 2001- Xuemei Xi, Mohan Dunga, Ali Niknejad, Chenming Hu.
 * Project Director: Prof. Chenming Hu.
 **********/

#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"
#include "bsim4v5def.h"
#include "ngspice/sperror.h"
#include "ngspice/suffix.h"


#ifdef USE_OMP
#include <omp.h>
#endif

static void
BSIM4v5truncInstance(BSIM4v5instance *here, CKTcircuit *ckt,
                      double *timeStep)
{
    CKTterr(here->BSIM4v5qb, ckt, timeStep);
    CKTterr(here->BSIM4v5qg, ckt, timeStep);
    CKTterr(here->BSIM4v5qd, ckt, timeStep);
    if (here->BSIM4v5trnqsMod)
        CKTterr(here->BSIM4v5qcdump, ckt, timeStep);
    if (here->BSIM4v5rbodyMod) {
        CKTterr(here->BSIM4v5qbs, ckt, timeStep);
        CKTterr(here->BSIM4v5qbd, ckt, timeStep);
    }
    if (here->BSIM4v5rgateMod == 3)
        CKTterr(here->BSIM4v5qgmid, ckt, timeStep);
}

int
BSIM4v5trunc(GENmodel *inModel, CKTcircuit *ckt, double *timeStep)
{
    BSIM4v5model *model = (BSIM4v5model *) inModel;
    BSIM4v5instance *here;
#ifdef STEPDEBUG
    double debugtemp;
#endif

#if defined(USE_OMP) && !defined(STEPDEBUG)
    /* CKTterr reads the fixed state history and only limits its argument.
     * Reuse the instance array of the parallel model evaluation and merge
     * one timestep per thread, keeping a minimum grain of 256 instances per requested thread. */
    const int threads = omp_get_max_threads();
    if (model && threads > 1 && model->BSIM4v5InstCount / threads >= 256) {
        const double initialStep = *timeStep;
        double limitedStep = initialStep;
        int index;
#pragma omp parallel
        {
            double localStep = initialStep;
#pragma omp for schedule(static)
            for (index = 0; index < model->BSIM4v5InstCount; index++)
                BSIM4v5truncInstance(model->BSIM4v5InstanceArray[index],
                                      ckt, &localStep);
#pragma omp critical
            {
                if (localStep < limitedStep)
                    limitedStep = localStep;
            }
        }
        *timeStep = limitedStep;
        return OK;
    }
#endif

    for (; model != NULL; model = BSIM4v5nextModel(model)) {
        for (here = BSIM4v5instances(model); here != NULL;
                here = BSIM4v5nextInstance(here)) {
#ifdef STEPDEBUG
            debugtemp = *timeStep;
#endif
            BSIM4v5truncInstance(here, ckt, timeStep);
#ifdef STEPDEBUG
            if (debugtemp != *timeStep)
                printf("device %s reduces step from %g to %g\n",
                       here->BSIM4v5name, debugtemp, *timeStep);
#endif
        }
    }
    return OK;
}
