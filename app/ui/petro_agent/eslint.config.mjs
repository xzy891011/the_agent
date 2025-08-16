import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // 禁用有问题的TypeScript ESLint规则
      "@typescript-eslint/no-explicit-any": "off",
      // 临时禁用React转义字符检查
      "react/no-unescaped-entities": "off",
      // 将React Hooks依赖警告降级为警告而不是错误
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];

export default eslintConfig;
