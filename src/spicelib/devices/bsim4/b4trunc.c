/* ******************************************************************************
   *  BSIM4 4.8.3 released on 05/19/2025                                        *
   *  BSIM4 Model Equations                                                     *
   ******************************************************************************

   ******************************************************************************
   *  Copyright (c) 2025 University of California                               *
   *                                                                            *
   *  Project Directors: Prof. Sayeef Salahuddin and Prof. Chenming Hu          *
   *  Developers list: https://www.bsim.berkeley.edu/models/bsim4/auth_bsim4/   *
   ******************************************************************************/

/*
Licensed under Educational Community License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain a copy of the license at
http://opensource.org/licenses/ECL-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations
under the License.

BSIM4 model is supported by the members of Silicon Integration Initiative's Compact Model Coalition. A link to the most recent version of this
standard can be found at: http://www.si2.org/cmc
*/

#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"
#include "bsim4def.h"
#include "ngspice/sperror.h"
#include "ngspice/suffix.h"

#ifdef USE_OMP
#include <omp.h>
#endif

static void
BSIM4truncInstance(BSIM4instance *here, CKTcircuit *ckt,
                      double *timeStep)
{
    CKTterr(here->BSIM4qb, ckt, timeStep);
    CKTterr(here->BSIM4qg, ckt, timeStep);
    CKTterr(here->BSIM4qd, ckt, timeStep);
    if (here->BSIM4trnqsMod)
        CKTterr(here->BSIM4qcdump, ckt, timeStep);
    if (here->BSIM4rbodyMod) {
        CKTterr(here->BSIM4qbs, ckt, timeStep);
        CKTterr(here->BSIM4qbd, ckt, timeStep);
    }
    if (here->BSIM4rgateMod == 3)
        CKTterr(here->BSIM4qgmid, ckt, timeStep);
}

int
BSIM4trunc(GENmodel *inModel, CKTcircuit *ckt, double *timeStep)
{
    BSIM4model *model = (BSIM4model *) inModel;
    BSIM4instance *here;
#ifdef STEPDEBUG
    double debugtemp;
#endif

#if defined(USE_OMP) && !defined(STEPDEBUG)
    /* CKTterr reads the fixed state history and only limits its argument.
     * Reuse the instance array of the parallel model evaluation and merge
     * one timestep per thread, keeping a minimum grain of 256 instances per requested thread. */
    const int threads = omp_get_max_threads();
    if (model && threads > 1 && model->BSIM4InstCount / threads >= 256) {
        const double initialStep = *timeStep;
        double limitedStep = initialStep;
        int index;
#pragma omp parallel
        {
            double localStep = initialStep;
#pragma omp for schedule(static)
            for (index = 0; index < model->BSIM4InstCount; index++)
                BSIM4truncInstance(model->BSIM4InstanceArray[index],
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

    for (; model != NULL; model = BSIM4nextModel(model)) {
        for (here = BSIM4instances(model); here != NULL;
                here = BSIM4nextInstance(here)) {
#ifdef STEPDEBUG
            debugtemp = *timeStep;
#endif
            BSIM4truncInstance(here, ckt, timeStep);
#ifdef STEPDEBUG
            if (debugtemp != *timeStep)
                printf("device %s reduces step from %g to %g\n",
                       here->BSIM4name, debugtemp, *timeStep);
#endif
        }
    }
    return OK;
}
