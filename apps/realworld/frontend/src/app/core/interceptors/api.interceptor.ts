import { HttpInterceptorFn } from "@angular/common/http";

// [agentic patch P1] Same-origin API (nginx proxies /api to the local backend)
// instead of the defunct public https://api.realworld.io.
export const apiInterceptor: HttpInterceptorFn = (req, next) => {
  const apiReq = req.clone({ url: `/api${req.url}` });
  return next(apiReq);
};
