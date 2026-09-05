// Protect the King - 2D. What it means to be something you can fight.

#pragma once

#include "CoreMinimal.h"
#include "Core/PTKTypes.h"
#include "UObject/Interface.h"
#include "PTKCombatTarget.generated.h"

class UPTKHealthComponent;

UINTERFACE(MinimalAPI)
class UPTKCombatTarget : public UInterface
{
	GENERATED_BODY()
};

/**
 * IPTKCombatTarget
 * ================
 * Implemented by anything that can be attacked: guards, enemies, the King, and
 * whatever damageable thing comes next.
 *
 *
 * WHY THIS EXISTS
 * ---------------
 * Combat used to identify its victims with `Cast<APTKTopDownCharacter>`, which
 * quietly made "can be fought" mean "inherits movement, input and a camera
 * rig". The King is a stationary AActor on purpose - he must never walk or be
 * possessed - so under that rule he could not be hit by anything, ever. The
 * enemy melee path skipped him before team was even considered.
 *
 * The wrong fix is to promote the King to a Character just so he can bleed.
 * The right one is to stop conflating the two ideas: being damageable is about
 * owning a health component and belonging to a side, and has nothing to do
 * with being able to move. This interface is that distinction, and it is
 * deliberately tiny - three questions, no behaviour.
 *
 * A future turret, barricade or objective can be fought by implementing this
 * and nothing else.
 */
class PROTECTTHEKING2D_API IPTKCombatTarget
{
	GENERATED_BODY()

public:
	/** The shared health component. Never a private copy - see UPTKHealthComponent. */
	virtual UPTKHealthComponent* GetCombatHealth() const = 0;

	/** Which side this actor fights for. */
	virtual EPTKTeam GetCombatTeam() const = 0;

	/** True once defeated. A corpse is not a target. */
	virtual bool IsCombatDead() const = 0;
};


/**
 * Free helpers, so no caller has to remember the interface dance.
 *
 * Kept as plain functions rather than a UBlueprintFunctionLibrary because they
 * are used in the melee inner loop, where a reflected call would be paid for
 * on every overlap of every swing.
 */
namespace PTKCombat
{
	/** The interface, or nullptr if this actor is not a combat target at all. */
	PROTECTTHEKING2D_API IPTKCombatTarget* From(AActor* Actor);
	PROTECTTHEKING2D_API const IPTKCombatTarget* From(const AActor* Actor);

	/**
	 * Are these two sides enemies?
	 *
	 * NOT "different team". Guards and the King are different teams but the
	 * same side - a rule of `A != B` would let Ravager's axe cut down the man
	 * he is defending the moment the King became a valid victim. The fight is
	 * Enemies against everyone else, so hostility is exactly "one of you is an
	 * Enemy and the other is not".
	 */
	PROTECTTHEKING2D_API bool AreHostile(EPTKTeam A, EPTKTeam B);

	/** Valid, alive, and owns a health component: worth swinging at. */
	PROTECTTHEKING2D_API bool IsEngageable(const AActor* Actor);

	/** IsEngageable, and on the opposing side to Viewer. */
	PROTECTTHEKING2D_API bool IsHostileTarget(const AActor* Viewer, const AActor* Actor);

	/** Health component of a combat target, or nullptr. */
	PROTECTTHEKING2D_API UPTKHealthComponent* GetHealth(AActor* Actor);
}
