import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";
import eslintNextPlugin from "@next/eslint-plugin-next";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  prettier,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
  ]),
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    plugins: {
      next: eslintNextPlugin,
    },
    rules: {
      ...eslintNextPlugin.configs.recommended.rules,
      ...eslintNextPlugin.configs["core-web-vitals"].rules,
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-undef": "error",
      "no-dupe-else-if": "error",
      "no-unsafe-optional-chaining": "error",

      eqeqeq: ["error", "always"],
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-var": "error",
      "prefer-const": "error",

      "react/jsx-key": "error",
      "react/button-has-type": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",

      "@next/next/no-img-element": "error",
      "@next/next/no-html-link-for-pages": "error",
    },
  },
]);

export default eslintConfig;
