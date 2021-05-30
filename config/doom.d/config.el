;;; $DOOMDIR/config.el -*- lexical-binding: t; -*-

;; Place your private configuration here! Remember, you do not need to run 'doom
;; sync' after modifying this file!


;; Some functionality uses this to identify you, e.g. GPG configuration, email
;; clients, file templates and snippets.
(setq user-full-name "Jack Michaud"
      user-mail-address "jack.a.michaud@gmail.com")

;; Doom exposes five (optional) variables for controlling fonts in Doom. Here
;; are the three important ones:
;;
;; + `doom-font'
;; + `doom-variable-pitch-font'
;; + `doom-big-font' -- used for `doom-big-font-mode'; use this for
;;   presentations or streaming.
;;
;; They all accept either a font-spec, font string ("Input Mono-12"), or xlfd
;; font string. You generally only need these two:
;; (setq doom-font (font-spec :family "monospace" :size 12 :weight 'semi-light)
;;       doom-variable-pitch-font (font-spec :family "sans" :size 13))

;; There are two ways to load a theme. Both assume the theme is installed and
;; available. You can either set `doom-theme' or manually load a theme with the
;; `load-theme' function. This is the default:
(setq doom-theme 'doom-one)

;;
;; If you use `org' and don't want your org files in the default location below,
;; change `org-directory'. It must be set before org loads!
(setq org-directory "~/org/")
(setq org-default-notes-file (concat org-directory "notes.org"))

;; This determines the style of line numbers in effect. If set to `nil', line
;; numbers are disabled. For relative line numbers, set this to `relative'.
(setq display-line-numbers-type 'relative)
(set-face-attribute 'default nil :height 100)


;; Here are some additional functions/macros that could help you configure Doom:
;;
;; - `load!' for loading external *.el files relative to this one
;; - `use-package!' for configuring packages
;; - `after!' for running code after a package has loaded
;; - `add-load-path!' for adding directories to the `load-path', relative to
;;   this file. Emacs searches the `load-path' when you load packages with
;;   `require' or `use-package'.
;; - `map!' for binding new keys
;;
;; To get information about any of these functions/macros, move the cursor over
;; the highlighted symbol at press 'K' (non-evil users must press 'C-c c k').
;; This will open documentation for it, including demos of how they are used.
;;
;; You can also try 'gd' (or 'C-c c d') to jump to their definition and see how
;; they are implemented.

(custom-declare-face '+org-todo-next '((t (:inherit (bold font-lock-keyword-face org-todo)))) "")

;(defun find-active-sprint ()
;  (let ((fpath "~/org/knock-todo.org"))
;    (find-file fpath)
;    (goto-char ))))
(after! (:and appt org notifications)
  :config
  (defun notify (title body)
    (notifications-notify :title title :body body :urgency "critical"))
  (setq appt-disp-window-function
        (lambda (min-to-appt new-time msg)
          ; Message is a string with text properties:
          ; https://www.gnu.org/software/emacs/manual/html_node/elisp/Text-Props-and-Strings.html#Text-Props-and-Strings
          (if (atom min-to-appt)
              (notify "Appointment"
                      (format "%S minutes: %S" min-to-appt (substring-no-properties msg)))
            (dolist (idx (number-sequence 0 (1- (length min-to-appt))))
              (notify "Appointment"
                      (format "%S minutes: %S" (nth idx min-to-appt) (nth idx (substring-no-properties msg))))))))
  (notify "Appointment Notifications" "Appointment notifications have been configured!")
  (setq appt-delete-window-function (lambda () t))
  (org-agenda-to-appt)
  (appt-activate t)
  (print "Configuring appt"))


(setq org-jira-working-dir "~/.cache/org-jira")
(after! org-jira
  :init
  (unless (file-directory-p org-jira-working-dir)
    (make-directory org-jira-working-dir))
  :config
  (setq jiralib-url "https://knockr.atlassian.net"))

(after! org
  ;(setq org-agenda-files (append org-agenda-files
  ;                               (directory-files-recursively
  ;                                org-jira-working-dir
  ;                                "org")))
  (setq org-appointments-file (concat org-directory "appts.org"))
  (setq org-capture-templates
        '(("d" "Diary" entry (file+olp+datetree (lambda () (concat org-directory "diary.org")))
           "* Diary Entry" :clock-in t :clock-resume t)
          ("n" "Note" entry (file+olp+datetree org-default-notes-file)
           "* %?\n%u\n%a\n")
          ("t" "todo" entry (file+olp+datetree org-default-notes-file)
           "* TODO %?\n%u\n%a\n")
          ("a" "Appointment" entry (file+olp+datetree org-appointments-file)
           "* TODO %^{due date}T %?\n%u\n\n" :clock-in t :clock-resume t)
          ("T" "Tickler " entry (file (lambda () (concat org-directory "tickler.org")))
           "* TODO %^{due date}T %?\n%u\n\n" :clock-in t :clock-resume t)
          ("s" "Standup" entry (file+headline (lambda () (concat org-directory "todo.org")) "Knock Standup")
           "* DONE Standup :MEETING:\n:PROPERTIES:\n:STATUS:   :runner: Standup\n:END:\n%t" :clock-in t :clock-resume t)
          ("p" "PR" entry (file+headline (lambda () (concat org-directory "todo.org")) "PRs")
           "* TODO %u PR for %? :PR: %^{TICKET}p" :clock-in t :clock-resume t)
          ("m" "Meeting" entry (file+headline (lambda () (concat org-directory "todo.org")) "Meetings")
           "* DONE Meeting with %? :MEETING:\n%t %^{STATUS}p" :clock-in t :clock-resume t)
          ("w" "Walk" entry (file+olp+datetree org-default-notes-file)
           "* DONE Walking the dog \n:PROPERTIES:\n:STATUS:   :walking-the-dog: Walking\n:END:\n%t" :clock-in t :clock-resume t)))
  (setq org-todo-keywords
        '((sequence "TODO(t)" "WAIT(w@/!)" "|" "DONE(d!)" "KILL(c@)")))
  (setq org-todo-keywords
        '((sequence
           "PROJ"
           "NEXT"
           "TODO"
           "STRT"
           "WAIT"
           "|"
           "DONE"
           "KILL"))
        org-todo-keyword-faces
        '(("STRT" . +org-todo-active)
          ("WAIT" . +org-todo-onhold)
          ("HOLD" . +org-todo-onhold)
          ("PROJ" . +org-todo-project)
          ("NEXT" . +org-todo-next)))
  (setq org-agenda-prefix-format '((agenda . "%i %-12:c%?-12t%-6e% s")
                                   (todo . " %i %-12:c")
                                   (tags . " %i %-12:c")
                                   (search . " %i %-12:c")))
  (add-hook 'after-save-hook 'org-agenda-to-appt)

  ; Babel
  (org-babel-do-load-languages
    'org-babel-load-languages
    '((dot . t)))

  )


(add-hook 'auto-save-hook 'org-save-all-org-buffers)

