# UX/UI Context v25.9.16.7.2.36

Focus: responsive sidebar shell fix.

Observed issue from UAT screenshots:
- Desktop/laptop with constrained width: sidebar navigation collapsed into two columns inside a narrow rail, causing labels such as `Tổng q...` and `Ngân ...`.
- Mobile emulation 430px: sidebar consumed excessive width/top area and created empty right-side space.

Fixed behavior:
- Desktop rail remains one-column grouped navigation.
- Tablet/mobile uses a horizontal scroll command strip bounded to `100vw`.
- Shell prevents page-level horizontal overflow.
- Session card is hidden on mobile, and the decorative brand badge is hidden on mobile.
