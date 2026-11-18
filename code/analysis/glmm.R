# Primary inferential model (Section III-F, Eq. 1 of the paper).
#
# Binomial GLMM at package-reference level:
#   logit P(h_ij = 1) = b0 + b1 Model + b2 Lang + b3 Diff + b4 Recency + b5 Source
#                       + b6 Guard + b7 Hindi + b8 (Guard x Hindi) + u_task + v_resp
# Odds ratios with Wald 95% CIs; Holm correction across hypotheses H1-H6.
#
# Usage: Rscript analysis/glmm.R references.csv tasks.csv
# Needs: install.packages(c("lme4", "dplyr"))

suppressPackageStartupMessages({
  library(lme4)
  library(dplyr)
})

args <- commandArgs(trailingOnly = TRUE)
refs_path  <- if (length(args) >= 1) args[1] else "references.csv"
tasks_path <- if (length(args) >= 2) args[2] else "tasks.csv"

refs  <- read.csv(refs_path,  stringsAsFactors = FALSE)
tasks <- read.csv(tasks_path, stringsAsFactors = FALSE)

d <- refs %>%
  filter(!label %in% c("NoThirdParty", "Ambiguous")) %>%
  left_join(tasks %>% select(task_id, difficulty, segment, source), by = "task_id") %>%
  mutate(
    hallucinated = as.integer(label == "Hallucinated"),
    model        = factor(model),
    lang         = factor(prog_language, levels = c("python", "javascript")),
    difficulty   = factor(difficulty, levels = c("easy", "medium", "hard")),
    recency      = factor(segment, levels = c("pre-2023", "2023")),
    source       = factor(source, levels = c("stackoverflow", "llm-generated")),
    guard        = as.integer(condition == "guardrail"),
    hindi        = as.integer(prompt_language == "hindi")
  )

cat("References analysed:", nrow(d), " hallucinated:", sum(d$hallucinated), "\n\n")

fit <- glmer(
  hallucinated ~ model + lang + difficulty + recency + source + guard * hindi +
    (1 | task_id) + (1 | response_id),
  data = d, family = binomial,
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)
print(summary(fit))

co <- summary(fit)$coefficients
ci <- confint(fit, method = "Wald", parm = "beta_")
res <- data.frame(
  term  = rownames(co),
  OR    = exp(co[, "Estimate"]),
  lo95  = exp(ci[rownames(co), 1]),
  hi95  = exp(ci[rownames(co), 2]),
  p_raw = co[, "Pr(>|z|)"],
  row.names = NULL
)

# Hypothesis tests. H4/H5 are one-sided (guardrail lowers, Hindi raises odds).
one_sided <- function(term, direction) {
  z <- co[term, "z value"]
  if (direction == "less") pnorm(z) else pnorm(z, lower.tail = FALSE)
}
open_term <- grep("^model", rownames(co), value = TRUE)
open_term <- tail(open_term, 1)  # set the open-weight model as the last factor level
hyp <- data.frame(
  hypothesis = c("H1 JavaScript > Python", "H2 Hard > Easy", "H3 Open-weight > proprietary",
                 "H4 Guardrail lowers odds", "H5 Hindi raises odds", "H6 Guardrail x Hindi"),
  term = c("langjavascript", "difficultyhard", open_term, "guard", "hindi", "guard:hindi"),
  p = c(co["langjavascript", "Pr(>|z|)"], co["difficultyhard", "Pr(>|z|)"],
        co[open_term, "Pr(>|z|)"], one_sided("guard", "less"), one_sided("hindi", "greater"),
        co["guard:hindi", "Pr(>|z|)"])
)
hyp$p_holm <- p.adjust(hyp$p, method = "holm")
hyp$OR <- exp(co[hyp$term, "Estimate"])

cat("\nFixed effects (odds ratios):\n");  print(res, digits = 3)
cat("\nHypothesis tests (Holm-adjusted):\n"); print(hyp, digits = 3)
cat("\nTask random-intercept variance:", as.data.frame(VarCorr(fit))$vcov[1], "\n")

write.csv(res, "glmm_fixed_effects.csv", row.names = FALSE)
write.csv(hyp, "glmm_hypotheses.csv", row.names = FALSE)
