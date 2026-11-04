# measurement.py — menu options, step by step

## 1. Set unitary and s0 input state
1. Ask which unitary N.
2. Move fixed waveplates (HWP/QWP_1, HWP/QWP_12, HWP/QWP_IN_2, HWP/QWP_OUT_2, HWP/QWP_TOM_1) to U_N's angles, beep, print "UNITARY READY".
3. Move HWP_IN/QWP_IN to s0_N, print "READY".

## 2. Collect statistics -> measurement()
1. Ask N.
2. Ask input state(s): single / multiple (comma-separated j's) / all.
3. Ask whether to sweep all 6 analyzer bases for this input, full collection time each, no plot (y/N).
4. Offer to (re)run background calibration if none on file / show last date.
5. Ask collection duration per setting; confirm or change.
6. Acquire a background row (20x5s bins, delays offset) and keep it for the saved file.
7. Move fixed waveplates to U_N's angles, beep.
8. Print the switch-dwell value to set manually for N.
9. For each input state j (round-robin across settings if the total run is long):
   - Move HWP_IN/QWP_IN to s_j.
   - If tomo: for each basis H/V/A/D/R/L, move TOM_1 and TOM_DUMP analyzer plates to that basis's angle, then collect.
   - If no tomo: collect at the current analyzer setting.
   - Collecting = repeatedly integrate counts for the configured bin length, appending one row per bin.
10. On Ctrl-C, stop early (keeps whatever rows were collected).
11. Save all rows to CSV + a JSON sidecar (delays, thresholds, background, calibration snapshot), notify, play a tune if the run took >5 min.

## 3. Test antilatch server connection -> ping_antilatch()
1. Open a TCP connection to the antilatch host:port.
2. Send a ping JSON message.
3. Wait for a reply.
4. Print connected/OK, no-reply, or unexpected-reply.

## 4. Tune channel delays
1. Ask which channels to tune (default LOOP_CHS, or include DUMP_CH).
2. Ask integration time per point (default per-channel).
3. Call tune_delays() with those.

## 5. Unlatch detectors
1. Call reset_detectors() over the antilatch server (cycles bias voltages).
2. Print confirmation.

## 6. Perform tomography (fast characterization sweep + plot) -> perform_tomo()
1. Ask N.
2. Ask input sweep: HVAD / HVADRL / single process state s0 / every process state for N / single H-V-A-D-R-L basis.
3. Ask which path: 1 (ch2 via TOM_1) / 2 (dump via OUT_2) / both.
4. Ask integration time per basis setting, print total estimated time.
5. Path 1 (if chosen): move fixed waveplates to U_N's angles (TOM_1 left free), beep; for each input label, set it, then sweep TOM_1 through H/V/A/D/R/L recording ch2 coincidences; plot measured vs. theoretical U, get a fit residual.
6. Path 2 (if chosen): move fixed waveplates to U_N's angles (OUT_2 left free); swap the dump channel's delay to the 1-loop value; for each input label, set it, then sweep OUT_2 through H/V/A/D/R/L recording dump coincidences; restore the dump delay; plot and fit.
7. Print each path's fit residual, notify.

## 7. Check single input/output projector (phase tuning) -> check_projector()
1. Ask N.
2. Ask path (1 or 2).
3. Ask input (a basis, or a process state s_j).
4. Ask output basis.
5. Ask stream duration (blank = until Ctrl-C).
6. Move fixed waveplates to U_N's angles for the chosen path.
7. Move HWP_IN/QWP_IN to the input.
8. Path 1: move TOM_1 to the output basis's analyzer angle, stream ch(LOOP_CHS[0])'s coincidence rate.
   Path 2: move OUT_2 to the output basis's analyzer angle, swap dump delay to the 1-loop value, stream the dump channel, then restore the dump delay.

## 8. Calibrate background noise -> calibrate_background()
1. Ask integration time per step (default 60 s).
2. Bump every detector channel's delay off its tuned value.
3. Acquire coincidence/singles counts across all channels for that duration.
4. Compute each channel's background rate (Hz).
5. Save data/{timestamp}_noise_calibration.json, print result, notify.

## 9. Calibrate loss -> calibrate_loss()
1. Load any existing (possibly partial) loss-calibration file so prior stages count as done.
2. Show a menu of 7 stages, each with its last-done date, plus "0. Compute & finish." Stages can be run in any order, any number of times:
   - **source**: park path-2 plates; prompt to plug herald+signal into detectors; ask the channel; scan to find the peak delay and record it; measure background at peak+15ns.
   - **source_dump**: park path-2 plates; prompt to plug signal into the dump detector; scan/record peak; measure background.
   - **ch2**: prompt to plug signal into the setup; set zero-loop bypass optics (input H, path-2 plates parked, manual H2/switch prompt); scan/record around the tuned ch2 delay.
   - **ch4**: set one-loop optics (input H, OUT_2 pass-through, IN_2 rotates H->V); prompt for switch dwell 120 ns; scan/record around the tuned ch4 delay.
   - **dump**: same one-loop optics; prompt to set switch to dump after 1 loop, dwell 60 ns; scan/record around the dump-after-1-loop delay.
   - **straight_to_dump**: input H, path-2 plates parked; prompt switch to 'man'; coarse-scan down from the herald delay to find the peak (first time only, else reuse); fine scan/record.
   - **input**: prompt to unplug the signal fiber before the switch into a detector; ask the channel; coarse-scan down from the herald delay (first time only, else reuse); fine scan/record. Run last — disturbs polarisation downstream.
   - Each run saves immediately to data/{timestamp}_loss_calibration.json.
3. On "0": if any stage is missing, report which and stop without computing.
4. Otherwise compute each stage's mean rate +/- SEM, then derive det_eff_dump, loss_input_to_setup, loss_per_loop_pass, loss_to_dump (errors propagated).
5. Save the final losses + rates, print them, notify.
