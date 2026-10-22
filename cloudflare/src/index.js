import { Container, getContainer } from "@cloudflare/containers";

export class SkinToneContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "30m";

  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = {
      PORT: "8080",
      FLASK_DEBUG: "0",
      REQUIRE_BUCKET: "1",
      S3_BUCKET_NAME: env.S3_BUCKET_NAME,
      S3_ENDPOINT_URL: env.S3_ENDPOINT_URL,
      S3_REGION: env.S3_REGION,
      S3_URL_STYLE: env.S3_URL_STYLE,
      S3_ACCESS_KEY_ID: env.S3_ACCESS_KEY_ID,
      S3_SECRET_ACCESS_KEY: env.S3_SECRET_ACCESS_KEY,
      SECRET_KEY: env.SECRET_KEY,
    };
  }
}

export default {
  async fetch(request, env) {
    return getContainer(env.SKIN_TONE_CONTAINER).fetch(request);
  },
};
