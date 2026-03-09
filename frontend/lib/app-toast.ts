export const APP_TOAST_EVENT = "ft:toast";

export type AppToastTone = "danger" | "info";

export interface AppToastDetail {
  message: string;
  tone?: AppToastTone;
}

export function showAppToast(detail: AppToastDetail) {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(new CustomEvent<AppToastDetail>(APP_TOAST_EVENT, { detail }));
}
