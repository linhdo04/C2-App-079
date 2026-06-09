import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().trim().min(1, "Vui lòng nhập email.").email("Email không hợp lệ."),
  password: z.string().min(1, "Vui lòng nhập mật khẩu."),
});

export const registerSchema = loginSchema.extend({
  name: z.string().trim().min(1, "Vui lòng nhập tên.").max(100, "Tên không được vượt quá 100 ký tự."),
  password: z.string().min(8, "Mật khẩu phải có ít nhất 8 ký tự.").max(128, "Mật khẩu không được vượt quá 128 ký tự."),
});

export const agentQuestionSchema = z.object({
  question: z.string().trim().min(1, "Vui lòng nhập câu hỏi."),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
export type RegisterFormValues = z.infer<typeof registerSchema>;
export type AuthFormValues = LoginFormValues & Partial<Pick<RegisterFormValues, "name">>;
export type AgentQuestionFormValues = z.infer<typeof agentQuestionSchema>;
