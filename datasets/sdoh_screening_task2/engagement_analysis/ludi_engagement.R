# LUDI screening: do patients speak more as they keep talking to LUDI?
# Per patient per session: total words, and total nouns + adjectives, in their answers.
# Average across patients per session, 95% CI bar charts, one-tailed paired t-tests.
# Put the 3 data files (screening_cohort_visits.csv, screening_cohort_messages.csv, LUMA.xlsx)
# in the same folder as this script, open it in RStudio and click Source.
# Packages: install.packages(c("readxl", "udpipe", "ggplot2", "writexl"))

library(readxl)
library(udpipe)
library(ggplot2)
library(writexl)

# ---- Settings ---------------------------------------------------------------
HERE <- dirname(rstudioapi::getSourceEditorContext()$path)   # the folder this script is in
OUT <- file.path(HERE, "results")                              # results are saved here

# Accounts whose login had a typo, linked by hand (see the account check in step 2)
MANUAL_LINKS <- c(account_6 = "S5", account_15 = "S2")

# ---- 1. Load the data (from the same folder as this script) -----------------
visits   <- read.csv(file.path(HERE, "screening_cohort_visits.csv"))
messages <- read.csv(file.path(HERE, "screening_cohort_messages.csv"))
official <- read_excel(file.path(HERE, "LUMA.xlsx"))

official <- official[!is.na(official$`Subject name`), ]
official$patient <- paste0("S", seq_len(nrow(official)))    # S1..S13 in list order

# ---- 2. Link each login account to a patient on the official list -----------
# Logins look like name-MMDDYYYY. Exact rule: name matches one of the patient's
# names AND the date matches their date of birth.
letters_only <- function(x) gsub("[^a-z]", "", tolower(x))

accounts <- sort(unique(visits$phone_pin), method = "radix")   # fixed order -> account_1, account_2 ...
account_code <- setNames(paste0("account_", seq_along(accounts)), accounts)
visits$account <- account_code[visits$phone_pin]

owner <- c()
for (pin in accounts) {
  name_part <- letters_only(sub("-[^-]*$", "", pin))
  dob_part  <- sub(".*-", "", pin)
  for (i in seq_len(nrow(official))) {
    names_i <- letters_only(strsplit(gsub(",", " ", official$`Subject name`[i]), "\\s+")[[1]])
    dob_i   <- format(as.Date(official$DOB[i]), "%m%d%Y")
    if (name_part %in% names_i && dob_part == dob_i) owner[account_code[pin]] <- official$patient[i]
  }
}
owner <- c(owner, MANUAL_LINKS)
visits$patient <- owner[visits$account]
cat("Accounts not linked:", sum(is.na(owner[account_code])), "\n")

# ---- 3. Keep study visits: on or after consent, and drop S9 -----------------
# S9 came only once (first session) and did not complete, so S9 is left out.
consent <- setNames(as.Date(official$`Consent Date`), official$patient)
visits$date <- as.Date(substr(visits$started_at, 1, 10))
visits <- visits[visits$date >= consent[visits$patient] & visits$patient != "S9", ]

# ---- 4. Sessions: each patient's 1st study day = session 1, 2nd = 2 ... ------
# Restarts on the same day count as the same session.
visits$session <- ave(as.numeric(visits$date), visits$patient,
                      FUN = function(d) match(d, sort(unique(d))))

# ---- 5. Answers: patient replies to a screening question --------------------
# LUDI's screening questions have a topic in question_category; greetings,
# "are you ready?", recap and goodbye do not.
msgs <- merge(messages, visits[, c("visit_id", "patient", "session")], by = "visit_id")
msgs <- msgs[order(msgs$visit_id, msgs$id), ]

# For every message, find the most recent LUDI turn in the same visit
is_ludi <- msgs$role == "assistant"
last_ludi <- ave(ifelse(is_ludi, seq_len(nrow(msgs)), 0), msgs$visit_id, FUN = cummax)
topic <- ifelse(is_ludi & !is.na(msgs$question_category) & msgs$question_category != "",
                msgs$question_category, NA)
msgs$replying_to <- ifelse(last_ludi > 0, topic[pmax(last_ludi, 1)], NA)

has_text <- !is.na(msgs$content) & trimws(msgs$content) != ""
answers <- msgs[msgs$role == "user" & has_text & !is.na(msgs$replying_to), ]
cat("Answers to screening questions:", nrow(answers), "\n")

# ---- 6. Count words and nouns + adjectives in each answer -------------------
answers$words <- lengths(strsplit(trimws(answers$content), "\\s+"))

# Part-of-speech tagging with the udpipe English model (downloaded once per run)
model <- udpipe_load_model(udpipe_download_model("english-ewt", model_dir = tempdir())$file_model)
tags <- as.data.frame(udpipe(data.frame(doc_id = answers$id, text = answers$content), object = model))
noun_adj <- table(factor(tags$doc_id[tags$upos %in% c("NOUN", "ADJ")], levels = answers$id))
answers$noun_adj <- as.numeric(noun_adj[as.character(answers$id)])

# ---- 7. Totals per patient per session, then the average across patients ----
totals <- aggregate(cbind(words, noun_adj) ~ patient + session, data = answers, FUN = sum)
totals <- totals[order(as.numeric(sub("S", "", totals$patient)), totals$session), ]

wide <- function(measure) {          # patients as rows, sessions as columns
  w <- reshape(totals[, c("patient", "session", measure)], idvar = "patient",
               timevar = "session", direction = "wide")
  names(w) <- c("patient", paste0("session_", 1:5))
  w
}
summarise <- function(measure) {     # mean and 95% CI per session
  do.call(rbind, lapply(1:5, function(s) {
    x <- totals[totals$session == s, measure]
    half <- qt(0.975, length(x) - 1) * sd(x) / sqrt(length(x))
    data.frame(session = s, n = length(x), mean = mean(x), ci_low = mean(x) - half, ci_high = mean(x) + half)
  }))
}
words_table <- wide("words");       words_summary <- summarise("words")
nounadj_table <- wide("noun_adj");  nounadj_summary <- summarise("noun_adj")
print(words_summary); print(nounadj_summary)

# ---- 8. Bar charts with 95% confidence intervals ----------------------------
dir.create(OUT, showWarnings = FALSE)
bar_chart <- function(summary, title, ylabel, file) {
  p <- ggplot(summary, aes(factor(session), mean)) +
    geom_col(fill = "#2a78d6") +
    geom_errorbar(aes(ymin = ci_low, ymax = ci_high), width = 0.2) +
    geom_text(aes(label = round(mean, 1)), vjust = -0.5, nudge_x = 0.25) +
    labs(title = title, x = "Session", y = ylabel, caption = "Bars: mean across patients. Lines: 95% confidence interval.") +
    theme_minimal()
  ggsave(file.path(OUT, file), p, width = 7, height = 4, dpi = 200)
  print(p)
}
bar_chart(words_summary, "Average number of words per patient per session",
          "Words per patient", "words_per_session.png")
bar_chart(nounadj_summary, "Average number of nouns + adjectives per patient per session",
          "Nouns + adjectives per patient", "noun_adj_per_session.png")

# ---- 9. One-tailed paired t-tests: is the later session greater? ------------
t_tests <- function(table) {
  pairs <- combn(1:5, 2)
  do.call(rbind, lapply(seq_len(ncol(pairs)), function(k) {
    a <- pairs[1, k]; b <- pairs[2, k]
    earlier <- table[[paste0("session_", a)]]; later <- table[[paste0("session_", b)]]
    r <- t.test(later, earlier, paired = TRUE, alternative = "greater")
    data.frame(comparison = paste0("session ", a, " vs ", b), n = sum(!is.na(earlier - later)),
               mean_earlier = mean(earlier), mean_later = mean(later),
               t = unname(r$statistic), df = unname(r$parameter), p_one_tailed = r$p.value)
  }))
}
words_tests <- t_tests(words_table);     print(words_tests)
nounadj_tests <- t_tests(nounadj_table); print(nounadj_tests)

# ---- 10. Save everything to Excel -------------------------------------------
write_xlsx(list("Words per patient" = words_table, "Words per session" = words_summary,
                "Words t-tests" = words_tests, "Noun+adj per patient" = nounadj_table,
                "Noun+adj per session" = nounadj_summary, "Noun+adj t-tests" = nounadj_tests),
           file.path(OUT, "ludi_engagement_results.xlsx"))
cat("Saved results to", OUT, "\n")
