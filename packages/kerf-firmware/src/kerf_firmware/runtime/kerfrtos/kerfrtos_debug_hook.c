/*
 * kerfrtos_debug_hook.c — RTOS debug-side hook for JTAG/SWD inspection.
 *
 * This file is compiled into the kerfrtos target firmware.  It maintains a
 * small, GDB-readable table of live task and mutex state that the host-side
 * kerf_firmware.debug.rtos_inspect module can read over JTAG/SWD via
 * arm-none-eabi-gdb.
 *
 * The debug hook does NOT use dynamic allocation; all tables are statically
 * sized.  Symbol names are stable so the host Python layer can reference them
 * by name in GDB expressions.
 *
 * Usage
 * -----
 * 1. Include this file in the firmware build alongside the kerfrtos scheduler.
 * 2. Call kerfrtos_debug_register_task() / kerfrtos_debug_update_task() from
 *    the scheduler when task state changes.
 * 3. Call kerfrtos_debug_register_mutex() / kerfrtos_debug_update_mutex() from
 *    the mutex acquire/release paths.
 * 4. The host GDB session reads kerfrtos_debug_task_table[N] and
 *    kerfrtos_debug_mutex_table[N] directly.
 *
 * BKPT trap
 * ---------
 * kerfrtos_debug_trigger_bkpt() can be called from an RTOS idle hook or
 * on-demand to pause execution so GDB can capture a clean snapshot.
 */

#include <stdint.h>
#include <string.h>

/* Maximum tracked tasks and mutexes. Increase if needed. */
#ifndef KERFRTOS_DEBUG_MAX_TASKS
#define KERFRTOS_DEBUG_MAX_TASKS  16
#endif

#ifndef KERFRTOS_DEBUG_MAX_MUTEXES
#define KERFRTOS_DEBUG_MAX_MUTEXES 8
#endif

/* Task state codes (must match host-side string mapping in rtos_inspect.py) */
typedef enum {
    KERFRTOS_TASK_READY     = 0,
    KERFRTOS_TASK_RUNNING   = 1,
    KERFRTOS_TASK_BLOCKED   = 2,
    KERFRTOS_TASK_SUSPENDED = 3,
    KERFRTOS_TASK_DELETED   = 4,
} kerfrtos_task_state_t;

/* -------------------------------------------------------------------------
 * Task table entry — read by GDB as:
 *   kerfrtos_debug_task_table[i].name
 *   kerfrtos_debug_task_table[i].state
 *   kerfrtos_debug_task_table[i].priority
 *   kerfrtos_debug_task_table[i].stack_high_water
 *   kerfrtos_debug_task_table[i].stack_size
 * ---------------------------------------------------------------------- */

typedef struct {
    char     name[32];
    uint8_t  state;          /* kerfrtos_task_state_t */
    uint8_t  priority;
    uint16_t stack_high_water;  /* bytes remaining at watermark */
    uint16_t stack_size;        /* total stack size in bytes */
    uint8_t  _pad[2];
} kerfrtos_debug_task_entry_t;

/* -------------------------------------------------------------------------
 * Mutex table entry — read by GDB as:
 *   kerfrtos_debug_mutex_table[i].name
 *   kerfrtos_debug_mutex_table[i].held_by   (task name or empty string)
 *   kerfrtos_debug_mutex_table[i].waiters   (comma-separated task names)
 * ---------------------------------------------------------------------- */

typedef struct {
    char name[32];
    char held_by[32];    /* task name of current holder, or "" */
    char waiters[128];   /* comma-separated list of waiting task names */
} kerfrtos_debug_mutex_entry_t;

/* -------------------------------------------------------------------------
 * Exported symbols — stable names referenced by rtos_inspect.py
 * ---------------------------------------------------------------------- */

volatile uint32_t kerfrtos_debug_task_count = 0;
volatile kerfrtos_debug_task_entry_t
    kerfrtos_debug_task_table[KERFRTOS_DEBUG_MAX_TASKS];

volatile uint32_t kerfrtos_debug_mutex_count = 0;
volatile kerfrtos_debug_mutex_entry_t
    kerfrtos_debug_mutex_table[KERFRTOS_DEBUG_MAX_MUTEXES];

/* -------------------------------------------------------------------------
 * API — called from the scheduler
 * ---------------------------------------------------------------------- */

/**
 * kerfrtos_debug_register_task — add a new task to the debug table.
 *
 * @param name       Task name (truncated to 31 chars).
 * @param priority   Task priority.
 * @param stack_size Total stack size in bytes.
 */
void kerfrtos_debug_register_task(const char *name,
                                   uint8_t priority,
                                   uint16_t stack_size)
{
    if (kerfrtos_debug_task_count >= KERFRTOS_DEBUG_MAX_TASKS) return;
    uint32_t idx = kerfrtos_debug_task_count;
    volatile kerfrtos_debug_task_entry_t *e = &kerfrtos_debug_task_table[idx];
    strncpy((char *)e->name, name, sizeof(e->name) - 1);
    e->name[sizeof(e->name) - 1] = '\0';
    e->state = (uint8_t)KERFRTOS_TASK_READY;
    e->priority = priority;
    e->stack_size = stack_size;
    e->stack_high_water = stack_size; /* initially all free */
    kerfrtos_debug_task_count++;
}

/**
 * kerfrtos_debug_update_task — update state and stack watermark for a task.
 *
 * @param name              Task name (used as key).
 * @param state             New task state.
 * @param stack_high_water  Current stack watermark (bytes remaining).
 */
void kerfrtos_debug_update_task(const char *name,
                                 kerfrtos_task_state_t state,
                                 uint16_t stack_high_water)
{
    for (uint32_t i = 0; i < kerfrtos_debug_task_count; i++) {
        if (strncmp((const char *)kerfrtos_debug_task_table[i].name,
                    name, 32) == 0) {
            kerfrtos_debug_task_table[i].state = (uint8_t)state;
            kerfrtos_debug_task_table[i].stack_high_water = stack_high_water;
            return;
        }
    }
}

/**
 * kerfrtos_debug_register_mutex — add a mutex to the debug table.
 *
 * @param name  Mutex name (truncated to 31 chars).
 */
void kerfrtos_debug_register_mutex(const char *name)
{
    if (kerfrtos_debug_mutex_count >= KERFRTOS_DEBUG_MAX_MUTEXES) return;
    uint32_t idx = kerfrtos_debug_mutex_count;
    volatile kerfrtos_debug_mutex_entry_t *e = &kerfrtos_debug_mutex_table[idx];
    strncpy((char *)e->name, name, sizeof(e->name) - 1);
    e->name[sizeof(e->name) - 1] = '\0';
    e->held_by[0] = '\0';
    e->waiters[0] = '\0';
    kerfrtos_debug_mutex_count++;
}

/**
 * kerfrtos_debug_update_mutex — update holder and waiter list for a mutex.
 *
 * @param name     Mutex name (key).
 * @param held_by  Task name of current holder, or "" if free.
 * @param waiters  Comma-separated list of waiting task names, or "".
 */
void kerfrtos_debug_update_mutex(const char *name,
                                  const char *held_by,
                                  const char *waiters)
{
    for (uint32_t i = 0; i < kerfrtos_debug_mutex_count; i++) {
        if (strncmp((const char *)kerfrtos_debug_mutex_table[i].name,
                    name, 32) == 0) {
            strncpy((char *)kerfrtos_debug_mutex_table[i].held_by,
                    held_by, sizeof(kerfrtos_debug_mutex_table[i].held_by) - 1);
            kerfrtos_debug_mutex_table[i].held_by[
                sizeof(kerfrtos_debug_mutex_table[i].held_by) - 1] = '\0';
            strncpy((char *)kerfrtos_debug_mutex_table[i].waiters,
                    waiters, sizeof(kerfrtos_debug_mutex_table[i].waiters) - 1);
            kerfrtos_debug_mutex_table[i].waiters[
                sizeof(kerfrtos_debug_mutex_table[i].waiters) - 1] = '\0';
            return;
        }
    }
}

/**
 * kerfrtos_debug_trigger_bkpt — issue a software breakpoint.
 *
 * Used by the idle hook to signal GDB that a clean snapshot is available.
 * On Cortex-M, BKPT #0 halts the CPU and hands control to the attached
 * debugger.  If no debugger is attached and the debug monitor exception is
 * not enabled, the BKPT becomes a fault — do NOT call this in production
 * firmware without a debug-guard macro.
 */
void kerfrtos_debug_trigger_bkpt(void)
{
#if defined(__arm__) || defined(__thumb__)
    __asm volatile ("bkpt #0");
#elif defined(__riscv)
    __asm volatile ("ebreak");
#else
    /* x86 / host tests: do nothing */
    (void)0;
#endif
}
