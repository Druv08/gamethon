// Protect the King - 2D. What it means to be something you can fight.

#include "Combat/PTKCombatTarget.h"

#include "Components/PTKHealthComponent.h"
#include "GameFramework/Actor.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKCombatTarget)

namespace PTKCombat
{
	IPTKCombatTarget* From(AActor* Actor)
	{
		return Actor ? Cast<IPTKCombatTarget>(Actor) : nullptr;
	}

	const IPTKCombatTarget* From(const AActor* Actor)
	{
		return Actor ? Cast<IPTKCombatTarget>(Actor) : nullptr;
	}

	bool AreHostile(EPTKTeam A, EPTKTeam B)
	{
		// Enemies against everyone else. Guards and King are separate teams but
		// allies, which is why this is not a simple inequality.
		return (A == EPTKTeam::Enemies) != (B == EPTKTeam::Enemies);
	}

	bool IsEngageable(const AActor* Actor)
	{
		if (!IsValid(Actor))
		{
			return false;
		}
		const IPTKCombatTarget* const Combat = From(Actor);
		if (!Combat || Combat->IsCombatDead())
		{
			return false;
		}
		const UPTKHealthComponent* const Health = Combat->GetCombatHealth();
		return Health && !Health->IsDead();
	}

	bool IsHostileTarget(const AActor* Viewer, const AActor* Actor)
	{
		if (Actor == Viewer || !IsEngageable(Actor))
		{
			return false;
		}
		const IPTKCombatTarget* const Mine = From(Viewer);
		const IPTKCombatTarget* const Theirs = From(Actor);
		return Mine && Theirs && AreHostile(Mine->GetCombatTeam(), Theirs->GetCombatTeam());
	}

	UPTKHealthComponent* GetHealth(AActor* Actor)
	{
		IPTKCombatTarget* const Combat = From(Actor);
		return Combat ? Combat->GetCombatHealth() : nullptr;
	}
}
