/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true, // static site: data is baked in at build, Netlify rebuilds on each daily data commit
  images: { unoptimized: true },
};
export default nextConfig;
