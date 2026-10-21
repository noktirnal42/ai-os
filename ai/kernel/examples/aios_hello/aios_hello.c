// SPDX-License-Identifier: GPL-2.0
/* Example staged module: logs when it loads and unloads. It touches no hardware and no
 * other kernel state. Used to exercise the kstage build, test, request, and load flow. */
#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("AI OS example staged module");
MODULE_AUTHOR("AI OS");
MODULE_VERSION("0.1");

static int __init aios_hello_init(void)
{
	pr_info("aios_hello: loaded\n");
	return 0;
}

static void __exit aios_hello_exit(void)
{
	pr_info("aios_hello: unloaded\n");
}

module_init(aios_hello_init);
module_exit(aios_hello_exit);
