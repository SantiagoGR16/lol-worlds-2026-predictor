import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideEchartsCore } from 'ngx-echarts';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // ECharts se carga bajo demanda (chunk aparte): la pantalla de carga no lo espera.
    provideEchartsCore({ echarts: () => import('echarts') }),
  ],
};
